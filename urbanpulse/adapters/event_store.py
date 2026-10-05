"""PostgreSQL transaction boundaries for durable publication and consumer effects."""

import hashlib
import json
import math
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Connection, Engine

from urbanpulse.adapters.event_tables import attempts, cursors, deliveries, publications, receipts
from urbanpulse.application.durable_delivery import (
    MAX_ATTEMPTS,
    DeliveryClaim,
    EventTransaction,
    PublicationConflict,
    StaleClaim,
    TransactionAborted,
    receipt_from_wire,
    validate_key,
)
from urbanpulse.contracts.events import EventReceipt, RevisionOutcome, compare_revision


def clock(connection: Connection) -> datetime:
    return cast(datetime, connection.execute(select(func.clock_timestamp())).scalar_one())


def lock(connection: Connection, *identity: str) -> None:
    digest = hashlib.sha256(json.dumps(identity).encode()).digest()
    connection.exec_driver_sql(
        "SELECT pg_advisory_xact_lock(%s)", (int.from_bytes(digest[:8], signed=True),)
    )


def receipt(row: Mapping[Any, Any] | None) -> EventReceipt | None:
    if row is None:
        return None
    return EventReceipt(
        *(row[key] for key in ("source", "subject", "event_id", "revision", "fingerprint"))
    )


def values(event: EventReceipt) -> dict[str, Any]:
    return {
        key: getattr(event, key)
        for key in ("source", "subject", "event_id", "revision", "fingerprint")
    }


class PostgresEventTransaction:
    """Owning SQL repositories can bind to connection; application ports expose no SQL."""

    def __init__(self, connection: Connection) -> None:
        self.connection = connection
        self.failed = False

    def publish(self, context: str, wire: str, consumers: Sequence[str]) -> str:
        try:
            return self._publish(context, wire, consumers)
        except Exception:
            self.failed = True
            raise

    def _publish(self, context: str, wire: str, consumers: Sequence[str]) -> str:
        validate_key(context)
        if isinstance(consumers, str) or not consumers or len(set(consumers)) != len(consumers):
            raise ValueError("publication requires distinct registered consumers")
        for consumer in consumers:
            validate_key(consumer)
        targets = json.dumps(sorted(consumers), separators=(",", ":"))
        incoming = receipt_from_wire(wire)
        lock(self.connection, "publication", context)
        existing = (
            self.connection.execute(
                select(publications).where(
                    publications.c.context == context,
                    publications.c.source == incoming.source,
                    publications.c.event_id == incoming.event_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        if existing is not None:
            if receipt(existing) != incoming or existing["consumers"] != targets:
                raise PublicationConflict("event identity or registered consumer set changed")
            return str(existing["id"])
        aggregate = self.connection.execute(
            select(publications.c.id).where(
                publications.c.context == context,
                publications.c.source == incoming.source,
                publications.c.subject == incoming.subject,
                publications.c.revision == incoming.revision,
            )
        ).first()
        if aggregate is not None:
            raise PublicationConflict("aggregate revision already published with another event ID")
        publication_id = str(uuid4())
        self.connection.execute(
            publications.insert().values(
                id=publication_id,
                context=context,
                envelope=wire,
                consumers=targets,
                **values(incoming),
            )
        )
        self.connection.execute(
            deliveries.insert(),
            [
                {
                    "id": str(uuid4()),
                    "publication_id": publication_id,
                    "consumer": consumer,
                    "status": "pending",
                    "generation": 0,
                    "attempt_count": 0,
                }
                for consumer in sorted(consumers)
            ],
        )
        return publication_id

    def consume(
        self, context: str, consumer: str, wire: str, effect: Callable[[], None]
    ) -> RevisionOutcome:
        try:
            return self._consume(context, consumer, wire, effect)
        except Exception:
            self.failed = True
            raise

    def _consume(
        self, context: str, consumer: str, wire: str, effect: Callable[[], None]
    ) -> RevisionOutcome:
        validate_key(context)
        validate_key(consumer)
        incoming = receipt_from_wire(wire)
        # Bounded pilot: serialize one consumer context, including first-ever identities.
        lock(self.connection, "consumer", context, consumer)
        scope = {"context": context, "consumer": consumer, "source": incoming.source}
        prior = (
            self.connection.execute(select(receipts).filter_by(**scope, event_id=incoming.event_id))
            .mappings()
            .one_or_none()
        )
        current = (
            self.connection.execute(select(cursors).filter_by(**scope, subject=incoming.subject))
            .mappings()
            .one_or_none()
        )
        outcome = compare_revision(incoming, receipt(current), prior_receipt=receipt(prior))
        if outcome in (RevisionOutcome.DUPLICATE, RevisionOutcome.CONFLICT):
            return outcome
        if outcome == RevisionOutcome.APPLY:
            effect()
            statement = insert(cursors).values(
                context=context, consumer=consumer, **values(incoming)
            )
            self.connection.execute(
                statement.on_conflict_do_update(
                    index_elements=[
                        cursors.c.context,
                        cursors.c.consumer,
                        cursors.c.source,
                        cursors.c.subject,
                    ],
                    set_={
                        key: getattr(incoming, key)
                        for key in ("event_id", "revision", "fingerprint")
                    },
                )
            )
        self.connection.execute(
            receipts.insert().values(
                context=context, consumer=consumer, outcome=outcome.value, **values(incoming)
            )
        )
        return outcome


class PostgresEventStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @contextmanager
    def transaction(self) -> Iterator[PostgresEventTransaction]:
        with self.engine.connect().execution_options(
            isolation_level="READ COMMITTED"
        ) as connection:
            with connection.begin():
                transaction = PostgresEventTransaction(connection)
                yield transaction
                if transaction.failed:
                    raise TransactionAborted("a failed event operation aborted this transaction")

    def claim(
        self, consumer: str, *, limit: int = 1, lease_seconds: float = 30
    ) -> tuple[DeliveryClaim, ...]:
        validate_key(consumer)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("claim limit must be between 1 and 100")
        if not math.isfinite(lease_seconds) or not 0 < lease_seconds <= 3600:
            raise ValueError("lease duration must be positive and at most one hour")
        claimed = []
        with self.transaction() as transaction:
            connection = transaction.connection
            rows = (
                connection.execute(
                    select(deliveries, publications.c.context)
                    .join(publications)
                    .where(
                        deliveries.c.consumer == consumer,
                        or_(
                            deliveries.c.status == "pending",
                            and_(
                                deliveries.c.status == "leased",
                                deliveries.c.lease_until <= func.clock_timestamp(),
                            ),
                        ),
                    )
                    .order_by(deliveries.c.created_at, deliveries.c.id)
                    .limit(limit)
                    .with_for_update(skip_locked=True, of=deliveries)
                )
                .mappings()
                .all()
            )
            for row in rows:
                now = clock(connection)
                if row["status"] == "leased":
                    connection.execute(
                        update(attempts)
                        .where(
                            attempts.c.delivery_id == row["id"],
                            attempts.c.generation == row["generation"],
                        )
                        .values(ended_at=now, outcome="lease-expired")
                    )
                if row["attempt_count"] >= MAX_ATTEMPTS:
                    connection.execute(
                        update(deliveries)
                        .where(deliveries.c.id == row["id"])
                        .values(
                            status="dead-letter", lease_until=None, outcome="attempts-exhausted"
                        )
                    )
                    continue
                generation = row["generation"] + 1
                deadline = now + timedelta(seconds=lease_seconds)
                connection.execute(
                    update(deliveries)
                    .where(deliveries.c.id == row["id"])
                    .values(
                        status="leased",
                        generation=generation,
                        attempt_count=row["attempt_count"] + 1,
                        lease_until=deadline,
                    )
                )
                connection.execute(
                    attempts.insert().values(
                        delivery_id=row["id"],
                        generation=generation,
                        started_at=now,
                        lease_until=deadline,
                    )
                )
                claimed.append(
                    DeliveryClaim(row["id"], generation, row["context"], consumer, deadline)
                )
        return tuple(claimed)

    def complete(
        self, claim: DeliveryClaim, effect: Callable[[EventTransaction, str], None]
    ) -> RevisionOutcome:
        with self.transaction() as transaction:
            connection = transaction.connection
            row = (
                connection.execute(
                    select(
                        deliveries,
                        publications.c.context,
                        publications.c.envelope,
                        publications.c.source,
                        publications.c.event_id,
                        publications.c.subject,
                        publications.c.revision,
                        publications.c.fingerprint,
                    )
                    .join(publications)
                    .where(deliveries.c.id == claim.delivery_id)
                    .with_for_update(of=deliveries)
                )
                .mappings()
                .one_or_none()
            )
            if (
                row is None
                or row["consumer"] != claim.consumer
                or row["context"] != claim.context
                or row["generation"] != claim.generation
            ):
                raise StaleClaim("delivery claim was replaced or does not exist")
            if row["status"] == "complete" or (
                row["status"] == "dead-letter" and row["outcome"] == RevisionOutcome.CONFLICT.value
            ):
                return RevisionOutcome(row["outcome"])
            if row["status"] != "leased" or row["lease_until"] <= clock(connection):
                raise StaleClaim("delivery claim is not active")
            wire = row["envelope"]
            if receipt_from_wire(wire) != receipt(row):
                raise ValueError("stored publication integrity mismatch")
            outcome = transaction.consume(
                row["context"], row["consumer"], wire, lambda: effect(transaction, wire)
            )
            # Work can outlive its lease even while this transaction holds its row lock.
            ended = clock(connection)
            if ended >= row["lease_until"]:
                raise StaleClaim(
                    "delivery lease expired during the effect; all changes rolled back"
                )
            connection.execute(
                update(deliveries)
                .where(deliveries.c.id == row["id"])
                .values(
                    status="dead-letter" if outcome == RevisionOutcome.CONFLICT else "complete",
                    lease_until=None,
                    outcome=outcome.value,
                )
            )
            connection.execute(
                update(attempts)
                .where(
                    attempts.c.delivery_id == row["id"],
                    attempts.c.generation == claim.generation,
                )
                .values(ended_at=ended, outcome=outcome.value)
            )
        return outcome

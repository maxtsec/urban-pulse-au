"""Persisted retry transitions and local operator inspection; never store exception text."""

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select, update

from urbanpulse.adapters.event_store import PostgresEventStore, clock
from urbanpulse.adapters.event_tables import attempts, deliveries, publications, replays
from urbanpulse.application.durable_delivery import (
    MAX_ATTEMPTS,
    DeliveryClaim,
    FailureCategory,
    ReplayReason,
    StaleClaim,
    retry_delay,
    validate_key,
)


class PostgresRecoveryStore(PostgresEventStore):
    def release_infrastructure(self, claim: DeliveryClaim) -> str:
        with self.transaction() as transaction:
            connection = transaction.connection
            row = (
                connection.execute(
                    select(deliveries, publications.c.context)
                    .join(publications)
                    .where(deliveries.c.id == claim.delivery_id)
                    .with_for_update(of=deliveries)
                )
                .mappings()
                .one_or_none()
            )
            if (
                row is None
                or row["generation"] != claim.generation
                or row["context"] != claim.context
                or row["consumer"] != claim.consumer
            ):
                raise StaleClaim("infrastructure claim was replaced or does not exist")
            # A lost commit acknowledgement may hide a successful completion or failure record.
            if row["status"] != "leased":
                return str(row["outcome"] or row["status"])
            now = clock(connection)
            connection.execute(
                update(deliveries)
                .where(deliveries.c.id == claim.delivery_id)
                .values(
                    status="retry",
                    outcome="infrastructure-error",
                    lease_until=None,
                    attempt_count=row["attempt_count"] - 1,
                    available_at=now + timedelta(seconds=1),
                )
            )
            connection.execute(
                update(attempts)
                .where(
                    attempts.c.delivery_id == claim.delivery_id,
                    attempts.c.generation == claim.generation,
                )
                .values(ended_at=now, outcome="infrastructure-error")
            )
        return "infrastructure-error"

    def fail(self, claim: DeliveryClaim, category: FailureCategory) -> str:
        category = FailureCategory(category)
        with self.transaction() as transaction:
            connection = transaction.connection
            row = (
                connection.execute(
                    select(deliveries, publications.c.context)
                    .join(publications)
                    .where(deliveries.c.id == claim.delivery_id)
                    .with_for_update(of=deliveries)
                )
                .mappings()
                .one_or_none()
            )
            if (
                row is None
                or row["generation"] != claim.generation
                or row["context"] != claim.context
                or row["consumer"] != claim.consumer
            ):
                raise StaleClaim("failure claim was replaced or does not exist")
            if row["status"] in ("retry", "dead-letter") and row["outcome"] == category.value:
                return str(row["status"])
            now = clock(connection)
            if row["status"] != "leased" or row["lease_until"] <= now:
                raise StaleClaim("failure claim is not active")
            terminal = category != FailureCategory.HANDLER or row["attempt_count"] >= MAX_ATTEMPTS
            status = "dead-letter" if terminal else "retry"
            due = now + timedelta(seconds=retry_delay(row["attempt_count"]))
            connection.execute(
                update(deliveries)
                .where(deliveries.c.id == claim.delivery_id)
                .values(
                    status=status,
                    outcome=category.value,
                    lease_until=None,
                    available_at=due,
                )
            )
            connection.execute(
                update(attempts)
                .where(
                    attempts.c.delivery_id == claim.delivery_id,
                    attempts.c.generation == claim.generation,
                )
                .values(ended_at=now, outcome=category.value)
            )
        return status

    def replay(self, delivery_id: str, expected_generation: int, reason: ReplayReason) -> int:
        reason = ReplayReason(reason)
        with self.transaction() as transaction:
            connection = transaction.connection
            row = (
                connection.execute(
                    select(deliveries).where(deliveries.c.id == delivery_id).with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise LookupError("unknown delivery")
            if row["generation"] != expected_generation or row["status"] not in (
                "complete",
                "dead-letter",
            ):
                raise StaleClaim("replay requires the inspected terminal generation")
            generation = row["generation"] + 1
            connection.execute(
                replays.insert().values(
                    delivery_id=delivery_id,
                    generation=generation,
                    reason=reason.value,
                )
            )
            connection.execute(
                update(deliveries)
                .where(deliveries.c.id == delivery_id)
                .values(
                    status="pending",
                    generation=generation,
                    attempt_count=0,
                    lease_until=None,
                    outcome=None,
                    available_at=clock(connection),
                )
            )
        return int(generation)

    def inspect(self, delivery_id: str) -> dict[str, Any]:
        with self.engine.connect().execution_options(
            isolation_level="REPEATABLE READ"
        ) as connection:
            with connection.begin():
                row = (
                    connection.execute(
                        select(
                            deliveries,
                            publications.c.context,
                            publications.c.source,
                            publications.c.event_id,
                        )
                        .join(publications)
                        .where(deliveries.c.id == delivery_id)
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    raise LookupError("unknown delivery")
                history = [
                    dict(item)
                    for item in connection.execute(
                        select(replays)
                        .where(replays.c.delivery_id == delivery_id)
                        .order_by(replays.c.generation)
                    ).mappings()
                ]
                attempted = [
                    dict(item)
                    for item in connection.execute(
                        select(attempts)
                        .where(attempts.c.delivery_id == delivery_id)
                        .order_by(attempts.c.generation)
                    ).mappings()
                ]
                for attempt in attempted:
                    attempt["replay_generation"] = max(
                        (
                            replay["generation"]
                            for replay in history
                            if replay["generation"] <= attempt["generation"]
                        ),
                        default=None,
                    )
                return {**dict(row), "attempts": attempted, "replays": history}

    def list_deliveries(self, context: str, *, limit: int = 100) -> list[dict[str, Any]]:
        validate_key(context)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("inspection limit must be between 1 and 100")
        with self.engine.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    select(
                        deliveries.c.id,
                        deliveries.c.consumer,
                        deliveries.c.status,
                        deliveries.c.generation,
                        deliveries.c.attempt_count,
                        deliveries.c.available_at,
                        deliveries.c.outcome,
                    )
                    .join(publications)
                    .where(publications.c.context == context)
                    .order_by(deliveries.c.created_at, deliveries.c.id)
                    .limit(limit)
                ).mappings()
            ]

    def metrics(self, consumer: str) -> dict[str, Any]:
        validate_key(consumer)
        with self.engine.connect() as connection:
            rows = (
                connection.execute(
                    select(
                        deliveries.c.status,
                        func.count().label("count"),
                        func.min(deliveries.c.created_at).label("oldest"),
                    )
                    .where(deliveries.c.consumer == consumer)
                    .group_by(deliveries.c.status)
                )
                .mappings()
                .all()
            )
            now = clock(connection)
        counts = {row["status"]: row["count"] for row in rows}
        pending = [row for row in rows if row["status"] in ("pending", "leased", "retry")]
        return {
            "consumer": consumer,
            "counts": counts,
            "backlog_count": sum(row["count"] for row in pending),
            "backlog_age_seconds": max(
                (max(0, (now - row["oldest"]).total_seconds()) for row in pending), default=0
            ),
            "retry_count": counts.get("retry", 0),
            "dead_letter_count": counts.get("dead-letter", 0),
        }

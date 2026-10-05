"""Real PostgreSQL atomic publication, independent claims and receipt/effect transactions."""

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from urbanpulse.adapters.city_store import engine_for, migrate
from urbanpulse.adapters.event_store import PostgresEventStore
from urbanpulse.adapters.event_tables import attempts, cursors, deliveries, publications, receipts
from urbanpulse.application.durable_delivery import (
    PublicationConflict,
    StaleClaim,
    TransactionAborted,
)
from urbanpulse.contracts.events import RevisionOutcome

pytestmark = pytest.mark.integration
URL = os.environ.get(
    "URBANPULSE_TEST_DATABASE_URL",
    "postgresql://urbanpulse:urbanpulse_local@127.0.0.1:5432/urbanpulse",
)


@pytest.fixture
def store():
    schema = "event_test_" + uuid4().hex
    admin = engine_for(URL)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = make_url(URL).update_query_dict({"options": f"-csearch_path={schema}"})
    private_url = url.render_as_string(hide_password=False)
    engine = engine_for(private_url)
    try:
        migrate(private_url)
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE test_effects (value text NOT NULL)"))
        yield PostgresEventStore(engine)
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def wire():
    return (Path(__file__).parents[1] / "fixtures/vehicle-position-event.json").read_text()


def changed(wire, *, revision=None, event_id=None, trace=None):
    value = json.loads(wire)
    if revision is not None:
        value["data"]["revision"] = revision
    if event_id is not None:
        value["id"] = event_id
    if trace is not None:
        value["traceparent"] = trace
    return json.dumps(value)


def effect(transaction, wire=""):
    transaction.connection.execute(text("INSERT INTO test_effects VALUES ('applied')"))


def count(store, table):
    with store.engine.connect() as connection:
        return connection.execute(select(func.count()).select_from(table)).scalar_one()


def effects(store):
    with store.engine.connect() as connection:
        return connection.execute(text("SELECT count(*) FROM test_effects")).scalar_one()


def publish(store, wire, consumers=("location-v1",), context="run-1"):
    with store.transaction() as transaction:
        return transaction.publish(context, wire, consumers)


def expire(store, claim):
    with store.engine.begin() as connection:
        connection.execute(
            update(deliveries)
            .where(deliveries.c.id == claim.delivery_id)
            .values(lease_until=text("clock_timestamp() - interval '10 seconds'"))
        )


def test_domain_and_publication_roll_back_together(store, wire):
    with pytest.raises(RuntimeError):
        with store.transaction() as transaction:
            effect(transaction)
            transaction.publish("run-1", wire, ("location-v1", "audit-v1"))
            raise RuntimeError("producer died before commit")
    assert effects(store) == count(store, publications) == count(store, deliveries) == 0
    with store.transaction() as transaction:
        effect(transaction)
        transaction.publish("run-1", wire, ("location-v1", "audit-v1"))
    assert effects(store) == count(store, publications) == 1
    assert count(store, deliveries) == 2


def test_concurrent_duplicate_publication_preserves_first_bytes_and_consumer_set(store, wire):
    first = publish(store, wire, ("location-v1", "audit-v1"))
    alternate = changed(wire, trace="00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01")
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(
            pool.map(lambda _: publish(store, alternate, ("audit-v1", "location-v1")), range(8))
        )
    assert set(ids) == {first}
    assert count(store, publications) == 1
    assert count(store, deliveries) == 2
    with store.engine.connect() as connection:
        assert connection.execute(select(publications.c.envelope)).scalar_one() == wire
    with pytest.raises(PublicationConflict):
        publish(store, wire, ("location-v1",))
    with pytest.raises(PublicationConflict):
        publish(store, changed(wire, revision=999), ("location-v1", "audit-v1"))
    with pytest.raises(PublicationConflict):
        publish(store, changed(wire, event_id="different-id"), ("location-v1", "audit-v1"))


def test_swallowed_publication_error_still_aborts_domain_transaction(store, wire):
    publish(store, wire)
    with pytest.raises(TransactionAborted):
        with store.transaction() as transaction:
            effect(transaction)
            try:
                transaction.publish("run-1", changed(wire, revision=99), ("location-v1",))
            except PublicationConflict:
                pass
    assert effects(store) == 0


def test_claims_are_unique_across_workers_and_consumers_are_independent(store, wire):
    for index in range(8):
        publish(
            store,
            changed(wire, event_id=f"event-{index}", revision=index + 1),
            ("location-v1", "audit-v1"),
        )
    barrier = threading.Barrier(4)

    def claim():
        barrier.wait(timeout=10)
        return store.claim("location-v1", limit=2)

    with ThreadPoolExecutor(max_workers=4) as pool:
        batches = list(pool.map(lambda _: claim(), range(4)))
    claimed = [item for batch in batches for item in batch]
    assert len({item.delivery_id for item in claimed}) == len(claimed) == 8
    assert store.claim("location-v1") == ()
    assert len(store.claim("audit-v1", limit=100)) == 8
    assert count(store, attempts) == 16


def test_effect_receipt_and_derived_publication_roll_back_then_commit_once(store, wire):
    publish(store, wire)
    claim = store.claim("location-v1")[0]
    derived = changed(wire, event_id="derived-fixture-event", revision=2)

    def fail(transaction, event):
        effect(transaction)
        transaction.publish("derived-run", derived, ("audit-v1",))
        raise RuntimeError("handler failed before receipt commit")

    with pytest.raises(RuntimeError):
        store.complete(claim, fail)
    assert effects(store) == count(store, receipts) == count(store, cursors) == 0
    assert count(store, publications) == 1

    def apply(transaction, event):
        effect(transaction)
        transaction.publish("derived-run", derived, ("audit-v1",))

    assert store.complete(claim, apply) == RevisionOutcome.APPLY
    assert (
        store.complete(claim, lambda *_: pytest.fail("already completed effect reran"))
        == RevisionOutcome.APPLY
    )
    assert effects(store) == count(store, receipts) == 1
    assert count(store, publications) == 2
    with store.engine.connect() as connection:
        assert connection.execute(select(attempts.c.outcome)).scalar_one() == "apply"


def test_duplicate_and_old_identity_conflict_precede_revision_ordering(store, wire):
    with store.transaction() as transaction:
        assert (
            transaction.consume("run-1", "location-v1", wire, lambda: effect(transaction))
            == RevisionOutcome.APPLY
        )
    with store.transaction() as transaction:
        newer = changed(wire, event_id="newer", revision=10)
        assert (
            transaction.consume("run-1", "location-v1", newer, lambda: effect(transaction))
            == RevisionOutcome.APPLY
        )
    for candidate, expected in [
        (
            changed(wire, trace="00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01"),
            RevisionOutcome.DUPLICATE,
        ),
        (changed(wire, revision=3), RevisionOutcome.CONFLICT),
        (changed(wire, event_id="older-distinct", revision=2), RevisionOutcome.SUPERSEDED),
    ]:
        with store.transaction() as transaction:
            assert (
                transaction.consume(
                    "run-1",
                    "location-v1",
                    candidate,
                    lambda: pytest.fail("non-current revision applied"),
                )
                == expected
            )
    assert effects(store) == 2
    assert count(store, receipts) == 3


def test_context_and_consumer_receipts_are_independent(store, wire):
    for context, consumer in [
        ("run-1", "location-v1"),
        ("run-2", "location-v1"),
        ("run-1", "audit-v1"),
    ]:
        with store.transaction() as transaction:
            transaction.consume(context, consumer, wire, lambda: effect(transaction))
    assert effects(store) == count(store, receipts) == 3


def test_expired_claim_is_fenced_after_reclaim_and_attempts_survive(store, wire):
    publish(store, wire)
    old = store.claim("location-v1")[0]
    expire(store, old)
    fresh_store = PostgresEventStore(store.engine)
    current = fresh_store.claim("location-v1")[0]
    assert current.generation == old.generation + 1
    with pytest.raises(StaleClaim):
        store.complete(old, lambda *_: pytest.fail("expired worker ran"))
    assert fresh_store.complete(current, effect) == RevisionOutcome.APPLY
    assert effects(store) == 1
    with store.engine.connect() as connection:
        assert list(
            connection.execute(select(attempts.c.outcome).order_by(attempts.c.generation)).scalars()
        ) == ["lease-expired", "apply"]


def test_claim_expiring_inside_effect_rolls_back_everything(store, wire):
    publish(store, wire)
    claim = store.claim("location-v1", lease_seconds=0.2)[0]

    def slow(transaction, event):
        effect(transaction)
        transaction.connection.execute(text("SELECT pg_sleep(0.25)"))

    with pytest.raises(StaleClaim):
        store.complete(claim, slow)
    assert effects(store) == count(store, receipts) == 0


def test_expired_attempt_budget_enters_dead_letter_without_affecting_other_consumer(store, wire):
    publish(store, wire, ("location-v1", "audit-v1"))
    for generation in range(1, 4):
        claim = store.claim("location-v1")[0]
        assert claim.generation == generation
        expire(store, claim)
    assert store.claim("location-v1") == ()
    assert store.complete(store.claim("audit-v1")[0], effect) == RevisionOutcome.APPLY
    with store.engine.connect() as connection:
        row = (
            connection.execute(select(deliveries).where(deliveries.c.consumer == "location-v1"))
            .mappings()
            .one()
        )
        assert row["status"] == "dead-letter"
        assert row["attempt_count"] == 3
    assert count(store, attempts) == 4


def test_concurrent_consumers_commit_only_one_effect_for_an_event(store, wire):
    barrier = threading.Barrier(2)

    def consume():
        barrier.wait(timeout=10)
        with store.transaction() as transaction:
            return transaction.consume("run-1", "location-v1", wire, lambda: effect(transaction))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: consume(), range(2)))
    assert sorted(results) == sorted([RevisionOutcome.APPLY, RevisionOutcome.DUPLICATE])
    assert effects(store) == count(store, receipts) == 1


def test_publication_corruption_cannot_create_an_effect(store, wire):
    publish(store, wire)
    claim = store.claim("location-v1")[0]
    with store.engine.begin() as connection:
        connection.execute(update(publications).values(envelope=changed(wire, revision=99)))
    with pytest.raises(ValueError, match="integrity"):
        store.complete(claim, effect)
    assert effects(store) == count(store, receipts) == 0


def test_simultaneous_first_publication_has_one_identity(store, wire):
    barrier = threading.Barrier(4)

    def start():
        barrier.wait(timeout=10)
        return publish(store, wire)

    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(lambda _: start(), range(4)))
    assert len(set(ids)) == count(store, publications) == count(store, deliveries) == 1


def test_claim_skips_a_locked_delivery_instead_of_waiting(store, wire):
    publish(store, wire)
    publish(store, changed(wire, event_id="second", revision=3))
    with store.engine.begin() as connection:
        locked = connection.execute(
            select(deliveries.c.id)
            .order_by(deliveries.c.created_at, deliveries.c.id)
            .limit(1)
            .with_for_update()
        ).scalar_one()
        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(store.claim, "location-v1").result(timeout=5)
        assert len(result) == 1 and result[0].delivery_id != locked
    assert store.claim("location-v1")[0].delivery_id == locked


def test_failed_consumer_operation_cannot_be_swallowed_and_committed(store, wire):
    def fail(transaction):
        effect(transaction)
        raise RuntimeError("partial local effect")

    with pytest.raises(TransactionAborted):
        with store.transaction() as transaction:
            try:
                transaction.consume("run-1", "location-v1", wire, lambda: fail(transaction))
            except RuntimeError:
                pass
    assert effects(store) == count(store, receipts) == count(store, cursors) == 0


@pytest.mark.parametrize("consumers", [(), ("location-v1", "location-v1"), ("",), "location-v1"])
def test_invalid_consumer_registration_rolls_back_owner_write(store, wire, consumers):
    with pytest.raises(ValueError):
        with store.transaction() as transaction:
            effect(transaction)
            transaction.publish("run-1", wire, consumers)
    assert effects(store) == count(store, publications) == 0


def test_claim_cannot_be_completed_as_a_different_consumer(store, wire):
    publish(store, wire, ("location-v1", "audit-v1"))
    claim = store.claim("location-v1")[0]
    with pytest.raises(StaleClaim):
        store.complete(replace(claim, consumer="audit-v1"), effect)
    assert effects(store) == count(store, receipts) == 0


def test_old_event_id_with_changed_subject_is_a_conflict(store, wire):
    with store.transaction() as transaction:
        transaction.consume("run-1", "location-v1", wire, lambda: effect(transaction))
    value = json.loads(wire)
    value["subject"] = value["data"]["state"]["vehicle_id"] = "different-vehicle"
    with store.transaction() as transaction:
        assert (
            transaction.consume(
                "run-1",
                "location-v1",
                json.dumps(value),
                lambda: pytest.fail("changed identity applied"),
            )
            == RevisionOutcome.CONFLICT
        )
    assert effects(store) == count(store, receipts) == 1


def test_claims_keep_publication_context_and_reject_a_changed_context(store, wire):
    publish(store, wire, context="run-a")
    publish(store, wire, context="run-b")
    claims = store.claim("location-v1", limit=2)
    assert {claim.context for claim in claims} == {"run-a", "run-b"}
    with pytest.raises(StaleClaim):
        store.complete(replace(claims[0], context="forged-run"), effect)
    assert effects(store) == 0
    for claim in claims:
        store.complete(claim, effect)
    assert effects(store) == count(store, receipts) == 2


def test_conflict_completion_is_repeatable_but_still_fences_claim_identity(store, wire):
    with store.transaction() as transaction:
        transaction.consume("run-1", "location-v1", wire, lambda: effect(transaction))
    publish(store, changed(wire, revision=3))
    claim = store.claim("location-v1")[0]

    def unexpected(*_):
        pytest.fail("conflict invoked the effect")

    assert store.complete(claim, unexpected) == RevisionOutcome.CONFLICT
    assert store.complete(claim, unexpected) == RevisionOutcome.CONFLICT
    for altered in (
        replace(claim, generation=claim.generation + 1),
        replace(claim, consumer="other-v1"),
        replace(claim, context="other-run"),
    ):
        with pytest.raises(StaleClaim):
            store.complete(altered, unexpected)
    assert effects(store) == count(store, receipts) == count(store, attempts) == 1
    with store.engine.connect() as connection:
        assert connection.execute(select(deliveries.c.status)).scalar_one() == "dead-letter"
        assert connection.execute(select(attempts.c.outcome)).scalar_one() == "conflict"


def test_exhausted_delivery_has_no_completion_to_repeat(store, wire):
    publish(store, wire)
    for _ in range(3):
        claim = store.claim("location-v1")[0]
        expire(store, claim)
    assert store.claim("location-v1") == ()
    with pytest.raises(StaleClaim):
        store.complete(claim, effect)
    assert effects(store) == count(store, receipts) == 0


def test_attempt_policy_upgrade_preserves_work_and_allows_a_larger_application_limit(
    store, wire, monkeypatch
):
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parents[2] / "migrations"))
    config.attributes["database_url"] = store.engine.url.render_as_string(hide_password=False)
    publication = publish(store, wire)
    for _ in range(3):
        claim = store.claim("location-v1")[0]
        expire(store, claim)
    command.downgrade(config, "0004_outbox_ledger")
    command.upgrade(config, "head")
    monkeypatch.setattr("urbanpulse.adapters.event_store.MAX_ATTEMPTS", 4)
    fourth = store.claim("location-v1")[0]
    assert fourth.generation == 4
    assert store.complete(fourth, effect) == RevisionOutcome.APPLY
    assert count(store, attempts) == 4
    with store.engine.connect() as connection:
        assert connection.execute(select(publications.c.id)).scalar_one() == publication
        assert connection.execute(select(deliveries.c.attempt_count)).scalar_one() == 4
    with pytest.raises(IntegrityError):
        with store.engine.begin() as connection:
            connection.execute(update(deliveries).values(attempt_count=-1))
    with pytest.raises(IntegrityError):
        command.downgrade(config, "0004_outbox_ledger")
    with store.engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0006_worker_recovery"
        )
        assert connection.execute(select(deliveries.c.attempt_count)).scalar_one() == 4

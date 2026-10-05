"""Per-consumer dependencies survive recovery without blocking other contexts."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from test_event_store import changed, count, effect, publish
from test_event_store import store as store
from test_event_store import wire as wire

from urbanpulse.adapters.event_recovery import PostgresRecoveryStore
from urbanpulse.adapters.event_tables import attempts, deliveries
from urbanpulse.application.durable_delivery import FailureCategory, ReplayReason

pytestmark = pytest.mark.integration


def config(store):
    value = Config()
    value.set_main_option("script_location", str(Path(__file__).parents[2] / "migrations"))
    value.attributes["database_url"] = store.engine.url.render_as_string(hide_password=False)
    return value


def publication_for(store, claim):
    with store.engine.connect() as connection:
        return connection.execute(
            select(deliveries.c.publication_id).where(deliveries.c.id == claim.delivery_id)
        ).scalar_one()


def test_dependency_is_independent_for_each_consumer_and_survives_replay(store, wire):
    consumers = ("location-v1", "audit-v1")
    with store.transaction() as transaction:
        first = transaction.publish("run-1", wire, consumers)
        second = transaction.publish(
            "run-1", changed(wire, revision=3, event_id="next"), consumers, after=first
        )
    location = store.claim("location-v1", limit=100)
    audit = store.claim("audit-v1", limit=100)
    assert len(location) == len(audit) == 1
    recovery = PostgresRecoveryStore(store.engine)
    recovery.fail(location[0], FailureCategory.INVALID)
    store.complete(audit[0], effect)
    assert publication_for(store, store.claim("audit-v1")[0]) == second
    assert store.claim("location-v1") == ()
    assert count(store, attempts) == 3
    recovery.replay(location[0].delivery_id, location[0].generation, ReplayReason.OPERATOR_RETRY)
    store.complete(store.claim("location-v1")[0], effect)
    assert publication_for(store, store.claim("location-v1")[0]) == second


@pytest.mark.parametrize("mismatch", ["context", "consumer"])
def test_dependency_cannot_cross_context_or_unregistered_consumer(store, wire, mismatch):
    first = publish(store, wire)
    with pytest.raises(ValueError, match="predecessor"):
        with store.transaction() as transaction:
            transaction.publish(
                "other" if mismatch == "context" else "run-1",
                changed(wire, revision=3, event_id="next"),
                ("other-v1",) if mismatch == "consumer" else ("location-v1",),
                after=first,
            )
    assert count(store, deliveries) == 1


def test_upgrade_preserves_pending_unordered_deliveries(store, wire):
    original = publish(store, wire)
    command.downgrade(config(store), "0006_worker_recovery")
    command.upgrade(config(store), "head")
    claim = store.claim("location-v1")[0]
    assert publication_for(store, claim) == original
    store.complete(claim, effect)


def test_downgrade_cannot_erase_dependency_history(store, wire):
    first = publish(store, wire)
    with store.transaction() as transaction:
        transaction.publish(
            "run-1", changed(wire, revision=3, event_id="next"), ("location-v1",), after=first
        )
    with pytest.raises(DBAPIError, match="history prevents downgrade"):
        command.downgrade(config(store), "0006_worker_recovery")
    assert count(store, deliveries) == 2
    with store.engine.connect() as connection:
        assert connection.execute(
            select(deliveries.c.predecessor_id).where(deliveries.c.predecessor_id.is_not(None))
        ).scalar_one()

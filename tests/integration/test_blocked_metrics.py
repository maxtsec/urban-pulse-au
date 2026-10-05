"""Dead-letter dependencies remain distinguishable from slow, runnable lanes."""

import pytest
from sqlalchemy import func, update
from test_event_store import changed, effect, publish
from test_event_store import store as store
from test_event_store import wire as wire

from urbanpulse.adapters.event_recovery import PostgresRecoveryStore
from urbanpulse.adapters.event_tables import deliveries
from urbanpulse.application.durable_delivery import FailureCategory, ReplayReason

pytestmark = pytest.mark.integration


def chain(store, wire):
    consumers = ("location-v1", "audit-v1")
    with store.transaction() as transaction:
        previous = None
        for revision in range(1, 5):
            previous = transaction.publish(
                "run-1",
                changed(wire, revision=revision, event_id=f"event-{revision}"),
                consumers,
                after=previous,
            )


def test_metrics_count_transitive_blocking_without_other_lanes_or_consumers(store, wire):
    chain(store, wire)
    queue = PostgresRecoveryStore(store.engine)
    head = queue.claim("location-v1")[0]
    assert queue.metrics("location-v1")["blocked_count"] == 0  # Leased is not terminal.
    queue.fail(head, FailureCategory.HANDLER)
    assert queue.metrics("location-v1")["blocked_count"] == 0  # Scheduled retry can recover.
    # The independent context stays runnable while the first lane is dead-lettered.
    with store.engine.begin() as connection:
        connection.execute(
            update(deliveries)
            .where(deliveries.c.id == head.delivery_id)
            .values(available_at=func.now())
        )
    head = queue.claim("location-v1")[0]
    queue.fail(head, FailureCategory.INVALID)
    publish(store, wire, context="independent")
    report = queue.metrics("location-v1")
    assert report["backlog_count"] == 4
    assert report["blocked_count"] == 3
    assert report["dead_letter_count"] == 1
    assert report["backlog_age_seconds"] >= 0
    assert queue.metrics("audit-v1")["blocked_count"] == 0
    assert queue.metrics("audit-v1")["backlog_count"] == 4
    assert queue.metrics("unregistered")["blocked_count"] == 0
    independent = queue.claim("location-v1")
    assert len(independent) == 1 and independent[0].context == "independent"
    queue.complete(independent[0], effect)
    queue.replay(head.delivery_id, head.generation, ReplayReason.OPERATOR_RETRY)
    assert queue.metrics("location-v1")["blocked_count"] == 0
    while claims := queue.claim("location-v1"):
        for claim in claims:
            queue.complete(claim, effect)
    assert queue.metrics("location-v1")["backlog_count"] == 0


def test_replayed_old_dead_letter_does_not_block_beyond_completed_successor(store, wire):
    chain(store, wire)
    queue = PostgresRecoveryStore(store.engine)
    head = queue.claim("location-v1")[0]
    queue.complete(head, effect)
    queue.complete(queue.claim("location-v1")[0], effect)
    queue.replay(head.delivery_id, head.generation, ReplayReason.OPERATOR_RETRY)
    # The replayed head and work beyond the completed successor are independently eligible.
    claims = queue.claim("location-v1", limit=100)
    replayed = next(claim for claim in claims if claim.delivery_id == head.delivery_id)
    queue.fail(replayed, FailureCategory.INVALID)
    report = queue.metrics("location-v1")
    assert report["dead_letter_count"] == 1
    assert report["backlog_count"] == 2
    assert report["blocked_count"] == 0

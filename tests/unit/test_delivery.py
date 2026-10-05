"""Delivery outcomes, atomic retries and typed composition boundaries."""

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from urbanpulse.application.city_replay import ServiceFrame
from urbanpulse.application.delivery import (
    CompositionUnavailable,
    HandlerResult,
    ProjectionHandler,
    RetryableHandlerError,
)
from urbanpulse.application.dispatch import InProcessPublisher
from urbanpulse.application.service_events import service_events
from urbanpulse.contracts.composition import TransportServiceStatusChanged
from urbanpulse.contracts.events import VehiclePositionChanged
from urbanpulse.location.city import PositionProjection


@pytest.fixture
def event():
    return VehiclePositionChanged.model_validate_json(
        Path("tests/fixtures/vehicle-position-event.json").read_text()
    )


def handler(apply=PositionProjection.consume):
    return ProjectionHandler(
        "positions", PositionProjection(), VehiclePositionChanged.model_validate_json, apply
    )


def test_failure_after_mutation_rolls_back_effect_receipt_and_counter(event):
    calls = 0

    def flaky(state, incoming):
        nonlocal calls
        calls += 1
        outcome = state.consume(incoming)
        if calls == 1:
            raise RetryableHandlerError()
        return outcome

    target = handler(flaky)
    waits = []
    publisher = InProcessPublisher("clock-a", waits.append)
    result = publisher.publish(event.model_dump_json(), [target])
    assert result["positions"].outcome == "applied"
    assert waits == [0.1]
    assert target.state.outcomes["apply"] == 1
    assert len(target.state.receipts) == 1
    assert [item["outcome"] for item in publisher.attempts] == ["retryable-failure", "applied"]


def test_exhaustion_is_bounded_and_does_not_rerun_successful_handlers(event):
    first = handler()

    def fail(state, incoming):
        state.consume(incoming)
        raise RetryableHandlerError()

    second = handler(fail)
    second.name = "failing"
    waits = []
    publisher = InProcessPublisher("clock-a", waits.append)
    with pytest.raises(CompositionUnavailable):
        publisher.publish(event.model_dump_json(), [first, second])
    assert first.state.outcomes["apply"] == 1
    assert second.state.positions == second.state.receipts == {}
    assert waits == [0.1, 0.25]
    assert [attempt["handler"] for attempt in publisher.attempts] == [
        "positions",
        "failing",
        "failing",
        "failing",
    ]


def test_terminal_rejection_is_not_retried_and_names_cannot_collide(event):
    publisher = InProcessPublisher("clock-a", lambda _: pytest.fail("unexpected retry"))
    target = handler()
    assert publisher.publish("null", [target])[target.name] == HandlerResult(
        "rejected", "invalid-envelope"
    )
    assert target.state.positions == {}
    with pytest.raises(ValueError, match="unique"):
        publisher.publish(event.model_dump_json(), [target, target])


def test_duplicate_trace_old_revision_and_changed_old_identity(event):
    target = handler()
    publisher = InProcessPublisher("clock-a")
    newer = event.model_dump(mode="json")
    newer["id"] += "-new"
    newer["data"]["revision"] += 1

    def publish(value):
        return publisher.publish(json.dumps(value), [target])[target.name]

    assert publish(newer).outcome == "applied"
    older = event.model_dump(mode="json")
    assert publish(older).outcome == "superseded"
    duplicate = copy.deepcopy(older)
    duplicate["traceparent"] = "00-changed-context"
    assert publish(duplicate).outcome == "duplicate"
    duplicate["data"]["state"]["route_id"] = "changed"
    assert publish(duplicate) == HandlerResult("rejected", "conflict")
    assert target.state.positions[event.subject].event.id == newer["id"]


def test_service_updates_preserve_episode_and_reveal_clear_only_when_received():
    start = datetime(2026, 10, 4, tzinfo=UTC)
    frames = tuple(
        ServiceFrame(
            id=f"frame-{at}",
            at_seconds=at,
            capture_ids=(f"capture-{at}",),
            stop_id="stop",
            status=status,
            reason=f"Reason {at}",
        )
        for at, status in [
            (0, "clear"),
            (60, "disrupted"),
            (90, "disrupted"),
            (180, "clear"),
            (240, "disrupted"),
        ]
    )
    events = service_events(frames, start, {"coordinates": [144.96, -37.82]})
    assert events[1].data.state.episode_id == events[2].data.state.episode_id == "frame-60"
    assert events[1].data.state.started_at == events[2].data.state.started_at
    assert events[2].data.state.resolved_at is None
    assert events[3].data.state.resolved_at == events[3].time
    assert events[4].data.state.episode_id == "frame-240"
    invalid = events[2].model_dump(mode="json")
    invalid["subject"] = "different-service"
    with pytest.raises(ValidationError):
        TransportServiceStatusChanged.model_validate(invalid)
    invalid = events[2].model_dump(mode="json")
    invalid["data"]["state"]["resolved_at"] = events[3].time
    with pytest.raises(ValidationError):
        TransportServiceStatusChanged.model_validate(invalid)

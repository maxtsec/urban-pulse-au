"""Fixture checkpoint plans and reconstruction from delivered integration envelopes."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from urbanpulse.application.city import (
    MAX_SECONDS,
    POLICY_VERSION,
    CityService,
    SpatialMembership,
    geometry_revision,
)
from urbanpulse.application.composition import transition_clocks
from urbanpulse.application.delivery import CompositionUnavailable, Handler, HandlerResult
from urbanpulse.application.dispatch import InProcessPublisher
from urbanpulse.application.durable_delivery import receipt_from_wire
from urbanpulse.application.event_worker import EventWorker, WorkerResult
from urbanpulse.application.inputs import CityInputs
from urbanpulse.application.scenarios import scenario_policy
from urbanpulse.contracts.events import VehiclePositionChanged
from urbanpulse.location.city import POSITION_EXPIRED_SECONDS, POSITION_STALE_SECONDS

CONSUMER = "city-location-v1"
RESULT_CONSUMER = "city-results-v1"
RUN_VERSION = "city-checkpoints-v1"


class CheckpointPublisher:
    """Record admitted events, or require their committed inbox copy during reconstruction."""

    def __init__(self, delivered: dict[tuple[str, str], str] | None = None) -> None:
        self.delivered = delivered
        self.accepted: dict[tuple[str, str], str] = {}
        self.publisher = InProcessPublisher("city-checkpoint")

    def publish(self, wire: str, handlers: Sequence[Handler]) -> dict[str, HandlerResult]:
        incoming = receipt_from_wire(wire)
        key = (incoming.source, incoming.event_id)
        stored = self.delivered.get(key) if self.delivered is not None else None
        matched = stored is not None and receipt_from_wire(stored) == incoming
        result = self.publisher.publish(
            stored if matched and stored is not None else wire, handlers
        )
        if any(item.outcome in ("applied", "duplicate") for item in result.values()):
            if self.delivered is not None and not matched:
                raise CompositionUnavailable("checkpoint input has not been delivered")
            prior = self.accepted.get(key)
            if prior is not None and receipt_from_wire(prior) != incoming:
                raise CompositionUnavailable("checkpoint has conflicting admitted identities")
            self.accepted.setdefault(key, wire)
        return result


@dataclass(frozen=True)
class CheckpointPlan:
    seconds: int
    wires: tuple[str, ...]


def clocks(inputs: CityInputs, target: int) -> list[int]:
    if type(target) is not int or not 0 <= target <= MAX_SECONDS:
        raise ValueError("checkpoint target must be an integer within the fixture clock")
    values = set(transition_clocks(inputs, target))
    started = datetime.fromisoformat(inputs.captured.scenario["started_at"])
    for frame in inputs.captured.scenario["frames"]:
        try:
            event = VehiclePositionChanged.model_validate(frame["event"])
        except ValueError:
            continue
        observed = event.data.state.observed_at
        if observed is not None:
            for threshold in (POSITION_STALE_SECONDS, POSITION_EXPIRED_SECONDS):
                values.add(math.ceil((observed - started).total_seconds() + threshold))
    return sorted(value for value in values if 0 <= value <= target)


class CityCheckpointModel:
    def __init__(self, inputs: CityInputs, spatial: SpatialMembership, scenario: str) -> None:
        scenario_policy(scenario)
        self.inputs = inputs
        self.spatial = spatial
        self.scenario = scenario
        self.boundary_revision = geometry_revision(inputs.captured.boundary["geometry"])
        self.rule_version = POLICY_VERSION

    def plan(self, seconds: int) -> CheckpointPlan:
        publisher = CheckpointPublisher()
        self.evaluate(seconds, publisher)
        return CheckpointPlan(seconds, tuple(publisher.accepted.values()))

    def evaluate(self, seconds: int, publisher: CheckpointPublisher) -> dict[str, Any]:
        return CityService(
            self.inputs,
            self.spatial,
            inputs=self.inputs,
            publisher_factory=lambda _: publisher,
        ).snapshot(seconds, self.scenario)


class CheckpointCoordinator(Protocol):
    def progress(self) -> bool: ...


class CityRunWorker:
    def __init__(
        self, coordinator: CheckpointCoordinator, inputs: EventWorker, results: EventWorker
    ) -> None:
        self.coordinator, self.inputs, self.results = coordinator, inputs, results

    def step(self) -> WorkerResult:
        progressed = self.coordinator.progress()
        result = self.inputs.step()
        if result.status != "idle":
            return result
        result = self.results.step()
        if result.status == "idle" and progressed:
            return WorkerResult("checkpoint")
        return result

"""Typed fixture service, coverage and derived area publication contracts."""

from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from urbanpulse.contracts.events import CloudEvent, Identifier, Position, Timestamp, WireModel


class InputRevision(WireModel):
    source: Identifier
    subject: Identifier
    event_id: Identifier
    revision: int = Field(strict=True, ge=1)


class TransportService(WireModel):
    service_id: Identifier
    stop_id: Identifier
    position: Position
    status: Literal["clear", "disrupted"]
    episode_id: Identifier | None
    started_at: Timestamp | None
    observed_at: Timestamp
    resolved_at: Timestamp | None
    reason: str = Field(min_length=1)


class TransportServiceStatusChanged(CloudEvent[TransportService]):
    type: Literal["au.urbanpulse.transport.service-status-changed.v1"]

    @model_validator(mode="after")
    def consistent_service(self) -> Self:
        state = self.data.state
        if self.source != "urn:urbanpulse:fixture:transport" or self.subject != state.service_id:
            raise ValueError("fixture transport service identity must match subject")
        if not self.data.provenance.capture_ids:
            raise ValueError("service status requires capture evidence")
        if (
            state.observed_at != self.time
            or self.data.provenance.source_observed_at != state.observed_at
        ):
            raise ValueError("service acceptance and fixture observation must agree")
        if (state.episode_id is None) != (state.started_at is None):
            raise ValueError("episode identity and start must be present together")
        if state.started_at is not None and state.started_at > state.observed_at:
            raise ValueError("episode cannot start after observation")
        if state.status == "disrupted" and (
            state.episode_id is None or state.resolved_at is not None
        ):
            raise ValueError("a disruption needs an unresolved episode")
        if (
            state.status == "clear"
            and state.episode_id is not None
            and state.resolved_at != state.observed_at
        ):
            raise ValueError("clear episode resolves at its received observation")
        if state.resolved_at is not None and (
            state.started_at is None or state.resolved_at < state.started_at
        ):
            raise ValueError("resolution needs a valid preceding episode")
        if self.data.effective_from != state.observed_at or self.data.effective_until is not None:
            raise ValueError("service state takes effect at observation without predicted expiry")
        return self


class SourceCoverage(WireModel):
    timeline_id: Identifier
    observation_id: Identifier
    input_id: Literal["transport_service", "weather_warnings", "planning"]
    state: Literal["current", "stale", "unknown", "unsupported", "error"]
    last_successful_received_at: Timestamp | None
    complete: bool
    products: tuple[Identifier, ...]
    input_revisions: tuple[InputRevision, ...]


class SourceCoverageChanged(CloudEvent[SourceCoverage]):
    type: Literal[
        "au.urbanpulse.transport.coverage-changed.v1",
        "au.urbanpulse.weather.coverage-changed.v1",
        "au.urbanpulse.planning.coverage-changed.v1",
    ]

    @model_validator(mode="after")
    def consistent_coverage(self) -> Self:
        state = self.data.state
        owner = {
            "transport_service": "transport",
            "weather_warnings": "weather",
            "planning": "planning",
        }[state.input_id]
        if (
            self.source != f"urn:urbanpulse:fixture:{owner}"
            or self.subject != f"coverage/{state.input_id}/{state.timeline_id}"
        ):
            raise ValueError("coverage owner and input identity must agree")
        if self.type != f"au.urbanpulse.{owner}.coverage-changed.v1":
            raise ValueError("coverage type must match owner")
        if (
            state.last_successful_received_at is not None
            and state.last_successful_received_at > self.time
        ):
            raise ValueError("coverage cannot expose a future successful receipt")
        if state.state == "current" and not state.complete:
            raise ValueError("current coverage must be complete")
        if len(set(state.products)) != len(state.products):
            raise ValueError("coverage products must be unique")
        if self.data.effective_from != self.time or self.data.effective_until is not None:
            raise ValueError("coverage starts at its evaluation time")
        return self


class AreaReason(WireModel):
    id: Identifier
    input_id: Literal["transport_service", "weather_warnings"]
    reason: str = Field(min_length=1)
    effective_from: Timestamp
    effective_until: Timestamp | None
    resolved_at: Timestamp | None

    @model_validator(mode="after")
    def valid_interval(self) -> Self:
        if self.effective_until is not None and self.effective_until <= self.effective_from:
            raise ValueError("reason expiry must follow its start")
        if self.resolved_at is not None and self.resolved_at < self.effective_from:
            raise ValueError("reason resolution cannot precede its start")
        return self


class AreaState(WireModel):
    timeline_id: Identifier
    area_id: Identifier
    condition: Literal["normal", "degraded", "unknown"]
    reasons: tuple[AreaReason, ...]
    coverage: tuple[SourceCoverage, ...]
    boundary_revision: Identifier
    rule_version: Identifier
    input_revisions: tuple[InputRevision, ...]
    evaluated_at: Timestamp

    @field_validator("reasons")
    @classmethod
    def ordered_reasons(cls, value: tuple[AreaReason, ...]) -> tuple[AreaReason, ...]:
        if len({reason.id for reason in value}) != len(value):
            raise ValueError("area reasons must be unique")
        return tuple(sorted(value, key=lambda reason: reason.id))

    @field_validator("coverage")
    @classmethod
    def ordered_coverage(cls, value: tuple[SourceCoverage, ...]) -> tuple[SourceCoverage, ...]:
        return tuple(sorted(value, key=lambda item: item.input_id))


class AreaStatusChanged(CloudEvent[AreaState]):
    type: Literal["au.urbanpulse.location.area-status-changed.v1"]

    @model_validator(mode="after")
    def consistent_area(self) -> Self:
        state = self.data.state
        if (
            self.source != "urn:urbanpulse:fixture:location"
            or self.subject != f"{state.area_id}/{state.timeline_id}"
        ):
            raise ValueError("fixture area subject must match area identity")
        if (
            self.time != state.evaluated_at
            or self.data.effective_from != state.evaluated_at
            or self.data.effective_until is not None
        ):
            raise ValueError("area evaluation and event times must agree")
        inputs = [item.input_id for item in state.coverage]
        if sorted(inputs) != ["transport_service", "weather_warnings"]:
            raise ValueError("area conditions require transport/weather coverage exactly once")
        if any(reason.input_id not in inputs for reason in state.reasons):
            raise ValueError("area reasons must belong to current-condition inputs")
        if any(
            reason.effective_from > self.time
            or reason.effective_until is not None
            and reason.effective_until <= self.time
            or reason.resolved_at is not None
            and reason.resolved_at <= self.time
            for reason in state.reasons
        ):
            raise ValueError("area reasons must be active at evaluation time")
        expected = (
            "degraded"
            if state.reasons
            else "normal"
            if all(item.state == "current" for item in state.coverage)
            else "unknown"
        )
        if state.condition != expected:
            raise ValueError("area condition must agree with reasons and coverage")
        return self

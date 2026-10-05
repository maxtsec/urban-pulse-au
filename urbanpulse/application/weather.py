"""Replay retained weather captures through normalization and published contracts."""

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from pydantic import TypeAdapter

from urbanpulse.application.delivery import ProjectionHandler, Publisher, revision_result
from urbanpulse.application.dispatch import InProcessPublisher
from urbanpulse.application.weather_replay import (
    WeatherEvent,
    WeatherNormalizer,
    WeatherStep,
    weather_steps,
)
from urbanpulse.contracts.events import RevisionOutcome
from urbanpulse.contracts.weather import PRODUCTS, ModelledReadingChanged
from urbanpulse.location.status import AdverseFact, CoverageState
from urbanpulse.location.weather import WarningMembership, WeatherProjection


def replay_weather(
    bundle: dict[str, Any],
    seconds: int,
    at: datetime,
    outage: bool,
    area: dict[str, Any],
    spatial: WarningMembership,
    normalizer: WeatherNormalizer | None,
    steps: Iterable[WeatherStep] | None = None,
    publisher: Publisher | None = None,
) -> tuple[dict[str, Any], tuple[AdverseFact, ...], CoverageState]:
    if steps is None:
        if normalizer is None:
            raise ValueError("weather inputs are unavailable")
        steps = weather_steps(bundle, seconds, at, outage, normalizer)
    publisher = publisher or InProcessPublisher("weather-fixture")
    handler: ProjectionHandler[WeatherProjection, WeatherEvent] = ProjectionHandler(
        "location.weather",
        WeatherProjection(),
        TypeAdapter(WeatherEvent).validate_json,
        WeatherProjection.consume,
    )
    projection = handler.state
    evidence: list[dict[str, Any]] = []
    rejected = 0
    last_received = None
    last_source_time = None
    state = CoverageState.UNKNOWN
    snapshot_ids: set[str] = set()
    snapshot_valid = False
    outage_at = bundle["outage_at_seconds"]
    reading = None
    for step in steps:
        frame = step.frame
        evidence.append(step.evidence)
        outcomes = [
            revision_result(publisher.publish(event.model_dump_json(), (handler,))[handler.name])
            for event in step.events
        ]
        projection = handler.state
        if frame["kind"] == "reading":
            event = step.events[0]
            assert isinstance(event, ModelledReadingChanged)
            if outcomes[0] == RevisionOutcome.APPLY:
                reading = {
                    **event.data.state.model_dump(mode="json"),
                    "received_at": frame["received_at"],
                    "provenance": event.data.provenance.model_dump(mode="json"),
                }
            continue
        if frame["kind"] == "coverage":
            state = CoverageState(frame["state"])
            continue
        if frame["kind"] == "redelivery":
            continue
        if frame["kind"] == "rejected":
            rejected += 1
            state = CoverageState.UNKNOWN
            snapshot_valid = False
            continue
        received = datetime.fromisoformat(frame["received_at"])
        snapshot_valid = (
            frame["complete"]
            and PRODUCTS <= frozenset(frame.get("products", []))
            and RevisionOutcome.CONFLICT not in outcomes
        )
        snapshot_ids = {event.subject for event in step.warning_records}
        for event in step.warning_records:
            current = projection.events.get((event.source, event.subject))
            if current is None or current.id != event.id or current.data != event.data:
                snapshot_valid = False
        capture_views, _, capture_understood = projection.warnings(received, area, spatial)
        capture_active = {
            view["id"] for view in capture_views if view["lifecycle"] in {"active", "scheduled"}
        }
        snapshot_valid = snapshot_valid and capture_understood and capture_active <= snapshot_ids
        last_received = frame["received_at"]
        last_source_time = frame["source_generated_at"]
        state = CoverageState.CURRENT if snapshot_valid else CoverageState.UNKNOWN
    if outage and seconds >= outage_at:
        state = CoverageState.ERROR
    warnings, facts, understood = projection.warnings(at, area, spatial)
    active_ids = {
        warning["id"] for warning in warnings if warning["lifecycle"] in {"active", "scheduled"}
    }
    if state == CoverageState.CURRENT and (
        not understood or not snapshot_valid or not active_ids <= snapshot_ids
    ):
        state = CoverageState.UNKNOWN
    return (
        {
            "mode": "fixture",
            "reading": reading,
            "warnings": warnings,
            "coverage": state,
            "last_feed_update_received_at": last_received,
            "source_generated_at": last_source_time,
            "coverage_policy": "authored-fixture-checkpoints-v1",
            "spatial_policy": "positive-area-overlap-v1",
            "attribution": {
                "owner": "State of Victoria",
                "notice_url": "https://www.emv.vic.gov.au/responsibilities/victorias-warning-system/emergency-data",
            },
            "projection": {**projection.outcomes, "rejected": rejected},
            "evidence": evidence,
        },
        facts,
        state,
    )

"""Replay retained weather captures through normalization and published contracts."""

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any, Protocol

from pydantic import ValidationError

from urbanpulse.contracts.events import RevisionOutcome
from urbanpulse.contracts.weather import PRODUCTS, ModelledReadingChanged, WeatherWarningChanged
from urbanpulse.location.status import AdverseFact, CoverageState
from urbanpulse.location.weather import WarningMembership, WeatherProjection


class WeatherNormalizer(Protocol):
    def warning(self, raw: dict[str, Any], capture: dict[str, Any]) -> WeatherWarningChanged: ...
    def reading(self, raw: dict[str, Any]) -> ModelledReadingChanged: ...


def payload_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def replay_weather(
    bundle: dict[str, Any],
    seconds: int,
    at: datetime,
    outage: bool,
    area: dict[str, Any],
    spatial: WarningMembership,
    normalizer: WeatherNormalizer,
) -> tuple[dict[str, Any], tuple[AdverseFact, ...], CoverageState]:
    projection = WeatherProjection()
    normalized: dict[str, WeatherWarningChanged] = {}
    sent: dict[str, WeatherWarningChanged] = {}
    evidence: list[dict[str, Any]] = []
    rejected = 0
    last_received = None
    last_source_time = None
    state = CoverageState.UNKNOWN
    snapshot_ids: set[str] = set()
    snapshot_valid = False
    outage_at = bundle["outage_at_seconds"]
    reading = None
    for raw in sorted(bundle["readings"], key=lambda item: item["at_seconds"]):
        if raw["at_seconds"] > seconds:
            continue
        reading_event = normalizer.reading(raw)
        if (
            reading_event.time != at + timedelta(seconds=raw["at_seconds"] - seconds)
            or reading_event.data.state.valid_at > reading_event.time
        ):
            raise ValueError("fixture reading cannot reveal a future observation")
        outcome = projection.consume(reading_event)
        if outcome == RevisionOutcome.APPLY:
            reading = {
                **reading_event.data.state.model_dump(mode="json"),
                "received_at": raw["received_at"],
                "provenance": reading_event.data.provenance.model_dump(mode="json"),
            }
        evidence.append(
            {
                "id": raw["capture_id"],
                "kind": "modelled-reading-capture",
                "at_seconds": raw["at_seconds"],
                "received_at": raw["received_at"],
                "payload_sha256": payload_hash(raw["state"]),
                "event_ids": [reading_event.id],
            }
        )
    for frame in sorted(bundle["frames"], key=lambda item: item["at_seconds"]):
        if frame["at_seconds"] > seconds or (outage and frame["at_seconds"] >= outage_at):
            continue
        kind = frame["kind"]
        if kind == "coverage":
            state = CoverageState(frame["state"])
            if state == CoverageState.CURRENT:
                raise ValueError("a coverage checkpoint cannot assert a successful fresh snapshot")
            evidence.append({**frame, "kind": "authored-coverage-checkpoint"})
            continue
        if kind == "redelivery":
            event = sent[frame["event_id"]]
            projection.consume(event)
            evidence.append({**frame, "kind": "event-redelivery"})
            continue
        payload = bundle["payloads"][frame["payload_id"]]
        received = datetime.fromisoformat(frame["received_at"])
        source_time = datetime.fromisoformat(frame["source_generated_at"])
        if (
            received != at + timedelta(seconds=frame["at_seconds"] - seconds)
            or source_time > received
        ):
            raise ValueError("fixture capture timestamps cannot reveal future data")
        events: list[str] = []
        snapshot_valid = frame["complete"] and frozenset(frame.get("products", [])) == PRODUCTS
        snapshot_ids = set()
        candidates: list[tuple[str, WeatherWarningChanged]] = []
        try:
            for raw in payload:
                digest = payload_hash(raw)
                candidate = normalized.get(digest)
                if candidate is None:
                    candidate = normalizer.warning(raw, frame)
                candidates.append((digest, candidate))
        except (ValidationError, KeyError, ValueError):
            rejected += 1
            state = CoverageState.UNKNOWN
            snapshot_valid = False
            evidence.append(
                {
                    "id": frame["id"],
                    "kind": "rejected-capture",
                    "at_seconds": frame["at_seconds"],
                    "payload_sha256": payload_hash(payload),
                }
            )
            continue
        for digest, event in candidates:
            if digest not in normalized:
                normalized[digest] = event
                outcome = projection.consume(event)
                if outcome.value == "conflict":
                    snapshot_valid = False
                sent.setdefault(event.id, event)
                events.append(event.id)
            snapshot_ids.add(event.subject)
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
        evidence.append(
            {
                "id": frame["id"],
                "kind": "warning-capture",
                "at_seconds": frame["at_seconds"],
                "received_at": last_received,
                "source_generated_at": last_source_time,
                "complete": frame["complete"],
                "payload_sha256": payload_hash(payload),
                "event_ids": events,
            }
        )
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

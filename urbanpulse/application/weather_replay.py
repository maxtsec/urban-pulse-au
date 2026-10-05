"""Normalize received fixture records and expose evidence without area or database work."""

import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

from urbanpulse.contracts.weather import ModelledReadingChanged, WeatherWarningChanged

WeatherEvent = WeatherWarningChanged | ModelledReadingChanged


class WeatherNormalizer(Protocol):
    def warning(self, raw: dict[str, Any], capture: dict[str, Any]) -> WeatherWarningChanged: ...
    def reading(self, raw: dict[str, Any]) -> ModelledReadingChanged: ...


@dataclass(frozen=True)
class WeatherStep:
    frame: dict[str, Any]
    evidence: dict[str, Any]
    events: tuple[WeatherEvent, ...] = ()
    warning_records: tuple[WeatherWarningChanged, ...] = ()


def payload_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def weather_steps(
    bundle: dict[str, Any],
    seconds: int,
    at: datetime,
    outage: bool,
    normalizer: WeatherNormalizer,
) -> Iterator[WeatherStep]:
    normalized: dict[str, WeatherWarningChanged] = {}
    sent: dict[str, WeatherWarningChanged] = {}
    for raw in sorted(bundle["readings"], key=lambda item: item["at_seconds"]):
        if raw["at_seconds"] > seconds:
            continue
        reading = normalizer.reading(raw)
        if (
            reading.time != at + timedelta(seconds=raw["at_seconds"] - seconds)
            or reading.data.state.valid_at > reading.time
        ):
            raise ValueError("fixture reading cannot reveal a future observation")
        yield WeatherStep(
            {**raw, "kind": "reading"},
            {
                "id": raw["capture_id"],
                "kind": "modelled-reading-capture",
                "at_seconds": raw["at_seconds"],
                "received_at": raw["received_at"],
                "payload_sha256": payload_hash(raw["state"]),
                "event_ids": [reading.id],
            },
            (reading,),
        )
    for frame in sorted(bundle["frames"], key=lambda item: item["at_seconds"]):
        if frame["at_seconds"] > seconds or (
            outage and frame["at_seconds"] >= bundle["outage_at_seconds"]
        ):
            continue
        if frame["kind"] == "coverage":
            if frame["state"] not in {"stale", "error", "unknown", "unsupported"}:
                raise ValueError("a coverage checkpoint cannot assert a fresh snapshot")
            yield WeatherStep(frame, {**frame, "kind": "authored-coverage-checkpoint"})
            continue
        if frame["kind"] == "redelivery":
            yield WeatherStep(
                frame, {**frame, "kind": "event-redelivery"}, (sent[frame["event_id"]],)
            )
            continue
        if frame["kind"] != "capture":
            raise ValueError("unknown fixture frame kind")
        # Broken bundle references are structural failures, not rejected provider records.
        payload = bundle["payloads"][frame["payload_id"]]
        received = datetime.fromisoformat(frame["received_at"])
        source_time = datetime.fromisoformat(frame["source_generated_at"])
        if (
            received != at + timedelta(seconds=frame["at_seconds"] - seconds)
            or source_time > received
        ):
            raise ValueError("fixture capture timestamps cannot reveal future data")
        candidates: list[tuple[str, WeatherWarningChanged]] = []
        try:
            for raw in payload:
                digest = payload_hash(raw)
                event = normalized.get(digest)
                candidates.append(
                    (digest, event if event is not None else normalizer.warning(raw, frame))
                )
        except (KeyError, ValueError):
            yield WeatherStep(
                {**frame, "kind": "rejected"},
                {
                    "id": frame["id"],
                    "kind": "rejected-capture",
                    "at_seconds": frame["at_seconds"],
                    "payload_sha256": payload_hash(payload),
                },
            )
            continue
        events: list[WeatherWarningChanged] = []
        for digest, event in candidates:
            if digest not in normalized:
                normalized[digest] = event
                sent.setdefault(event.id, event)
                events.append(event)
        yield WeatherStep(
            frame,
            {
                "id": frame["id"],
                "kind": "warning-capture",
                "at_seconds": frame["at_seconds"],
                "received_at": frame["received_at"],
                "source_generated_at": frame["source_generated_at"],
                "complete": frame["complete"],
                "payload_sha256": payload_hash(payload),
                "event_ids": [event.id for event in events],
            },
            tuple(events),
            tuple(event for _, event in candidates),
        )


def weather_evidence(
    bundle: dict[str, Any],
    seconds: int,
    at: datetime,
    outage: bool,
    normalizer: WeatherNormalizer,
) -> list[dict[str, Any]]:
    return [step.evidence for step in weather_steps(bundle, seconds, at, outage, normalizer)]

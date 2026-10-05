"""Normalize received fixture records and expose evidence without area or database work."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial
from typing import Any, Protocol

from urbanpulse.application.capture_replay import (
    CaptureHistory,
    capture_received_at,
    payload_hash,
    received_frames,
)
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


def weather_steps(
    bundle: dict[str, Any],
    seconds: int,
    at: datetime,
    outage: bool,
    normalizer: WeatherNormalizer,
) -> Iterator[WeatherStep]:
    history = CaptureHistory[WeatherWarningChanged]()
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
    for frame in received_frames(bundle, seconds, outage):
        if frame["kind"] == "coverage":
            if frame["state"] not in {"stale", "error", "unknown", "unsupported"}:
                raise ValueError("a coverage checkpoint cannot assert a fresh snapshot")
            yield WeatherStep(frame, {**frame, "kind": "authored-coverage-checkpoint"})
            continue
        if frame["kind"] == "redelivery":
            yield WeatherStep(
                frame,
                {**frame, "kind": "event-redelivery"},
                (history.redeliver(frame["event_id"]),),
            )
            continue
        if frame["kind"] != "capture":
            raise ValueError("unknown fixture frame kind")
        # Broken bundle references are structural failures, not rejected provider records.
        payload = bundle["payloads"][frame["payload_id"]]
        received = capture_received_at(frame, seconds, at)
        source_time = datetime.fromisoformat(frame["source_generated_at"])
        if source_time > received:
            raise ValueError("fixture capture timestamps cannot reveal future data")
        candidates: list[tuple[str, WeatherWarningChanged]] = []
        try:
            if not isinstance(payload, list):
                raise ValueError("warning payload must be an array")
            for raw in payload:
                if not isinstance(raw, dict):
                    raise ValueError("warning record must be an object")
                candidates.append(
                    history.prepare(payload_hash(raw), partial(normalizer.warning, raw, frame))
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
        events = history.commit(candidates)
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

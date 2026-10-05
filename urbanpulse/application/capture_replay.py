"""Shared fixture capture timing, hashing and atomic normalization history."""

import hashlib
import json
from collections.abc import Callable, Iterable, Iterator
from datetime import datetime, timedelta
from typing import Any

from urbanpulse.contracts.events import CloudEvent


def payload_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def received_frames(bundle: dict[str, Any], seconds: int, outage: bool) -> Iterator[dict[str, Any]]:
    for frame in sorted(bundle["frames"], key=lambda item: item["at_seconds"]):
        if frame["at_seconds"] <= seconds and not (
            outage and frame["at_seconds"] >= bundle["outage_at_seconds"]
        ):
            yield frame


def capture_received_at(frame: dict[str, Any], seconds: int, at: datetime) -> datetime:
    received = datetime.fromisoformat(frame["received_at"])
    if received != at + timedelta(seconds=frame["at_seconds"] - seconds):
        raise ValueError("fixture receipt must match the replay clock")
    return received


class CaptureHistory[Event: CloudEvent[Any]]:
    def __init__(self) -> None:
        self._normalized: dict[str, Event] = {}
        self._sent: dict[str, Event] = {}

    def prepare(self, digest: str, normalize: Callable[[], Event]) -> tuple[str, Event]:
        """Do not mutate history until every record in the capture has validated."""
        event = self._normalized.get(digest)
        return digest, event if event is not None else normalize()

    def commit(self, candidates: Iterable[tuple[str, Event]]) -> tuple[Event, ...]:
        events = []
        for digest, event in candidates:
            if digest not in self._normalized:
                self._normalized[digest] = event
                self._sent.setdefault(event.id, event)
                events.append(event)
        return tuple(events)

    def redeliver(self, event_id: str) -> Event:
        return self._sent[event_id]

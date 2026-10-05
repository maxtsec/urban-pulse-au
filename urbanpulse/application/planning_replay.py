"""Validate retained planning attempts; evidence has no projection or database dependency."""

import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

from urbanpulse.contracts.planning import PlanningSnapshotPublished


class PlanningNormalizer(Protocol):
    def snapshot(self, raw: dict[str, Any], frame: dict[str, Any]) -> PlanningSnapshotPublished: ...


@dataclass(frozen=True)
class PlanningStep:
    frame: dict[str, Any]
    evidence: dict[str, Any]
    event: PlanningSnapshotPublished | None = None
    recapture: bool = False


def planning_steps(
    bundle: dict[str, Any], seconds: int, at: datetime, outage: bool, normalizer: PlanningNormalizer
) -> Iterator[PlanningStep]:
    normalized: dict[str, PlanningSnapshotPublished] = {}
    sent: dict[str, PlanningSnapshotPublished] = {}
    for frame in sorted(bundle["frames"], key=lambda item: item["at_seconds"]):
        if frame["at_seconds"] > seconds or (
            outage and frame["at_seconds"] >= bundle["outage_at_seconds"]
        ):
            continue
        evidence = {"id": frame["id"], "at_seconds": frame["at_seconds"]}
        if frame["kind"] == "coverage":
            if frame["state"] not in {"stale", "error", "unknown"}:
                raise ValueError("planning checkpoint cannot establish complete coverage")
            yield PlanningStep(
                frame, {**evidence, "kind": "planning-coverage", "state": frame["state"]}
            )
            continue
        if frame["kind"] == "redelivery":
            event = sent[frame["event_id"]]
            yield PlanningStep(
                frame, {**evidence, "kind": "planning-redelivery", "event_ids": [event.id]}, event
            )
            continue
        if frame["kind"] != "capture":
            raise ValueError("unknown planning frame kind")
        raw = bundle["payloads"][frame["payload_id"]]
        if datetime.fromisoformat(frame["received_at"]) != at + timedelta(
            seconds=frame["at_seconds"] - seconds
        ):
            raise ValueError("planning receipt must match the replay clock")
        digest = hashlib.sha256(
            json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()
        evidence.update({"payload_sha256": digest, "received_at": frame["received_at"]})
        try:
            if not isinstance(raw, dict) or not isinstance(raw.get("complete"), bool):
                raise ValueError("planning capture requires an explicit snapshot declaration")
            if raw["complete"] is False:
                yield PlanningStep(
                    {**frame, "kind": "incomplete"},
                    {**evidence, "kind": "planning-incomplete-capture"},
                )
                continue
            recapture = digest in normalized
            event = normalized[digest] if recapture else normalizer.snapshot(raw, frame)
        except (KeyError, ValueError):
            yield PlanningStep(
                {**frame, "kind": "rejected"}, {**evidence, "kind": "planning-rejected-capture"}
            )
            continue
        normalized[digest] = event
        sent.setdefault(event.id, event)
        yield PlanningStep(
            frame,
            {
                **evidence,
                "kind": "planning-snapshot-capture",
                "snapshot_id": event.data.state.snapshot_id,
                "as_of": event.data.state.as_of,
                "event_ids": [] if recapture else [event.id],
            },
            event,
            recapture,
        )

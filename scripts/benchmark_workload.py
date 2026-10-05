"""Deterministic synthetic planning histories on the existing bounded city clock."""

from dataclasses import replace
from datetime import datetime, timedelta

from urbanpulse.application.capture_replay import payload_hash
from urbanpulse.application.city import CapturedCity

WORKLOAD_VERSION = "planning-history-v1"


def planning_history(base: CapturedCity, snapshots: int, records: int) -> CapturedCity:
    if not 1 <= snapshots <= 60 or not 1 <= records <= 1000:
        raise ValueError("use 1..60 snapshots and 1..1000 records per snapshot")
    started = datetime.fromisoformat(base.scenario["started_at"])
    frames = []
    payloads = {}
    for index in range(snapshots):
        seconds = index * 300 // max(1, snapshots - 1)
        identity = f"benchmark-planning-{index + 1}"
        frames.append(
            {
                "kind": "capture",
                "id": identity,
                "at_seconds": seconds,
                "received_at": (started + timedelta(seconds=seconds)).isoformat(),
                "payload_id": identity,
            }
        )
        payloads[identity] = {
            "event_id": identity,
            "snapshot_id": identity,
            "revision": index + 1,
            "as_of": (started - timedelta(days=snapshots - index)).isoformat(),
            "complete": True,
            "records": [
                {
                    "development_key": f"benchmark-development-{number:04d}",
                    "name": f"Synthetic benchmark development {number}",
                    "status": ("Applied", "Approved", "Under construction")[index % 3],
                    "clue_small_area": "Southbank",
                    "position": {"longitude": 144.961 + number * 0.000001, "latitude": -37.8225},
                    "year_completed": None,
                }
                for number in range(records)
            ],
        }
    bundle = {"mode": "fixture", "outage_at_seconds": 360, "frames": frames, "payloads": payloads}
    identity = payload_hash([WORKLOAD_VERSION, base.capture_id, bundle])
    return replace(base, capture_id=identity, planning=bundle)

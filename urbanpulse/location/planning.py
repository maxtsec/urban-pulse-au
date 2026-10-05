"""Location-owned planning profile with atomic snapshot replacement and audit history."""

import json
from datetime import datetime
from typing import Any, Protocol

from urbanpulse.contracts.events import EventReceipt, RevisionOutcome, compare_revision
from urbanpulse.contracts.planning import (
    PlanningRecord,
    PlanningSnapshot,
    PlanningSnapshotPublished,
)


def source_time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


class PlanningMembership(Protocol):
    def covers(self, geometry: dict[str, Any], points: list[tuple[float, float]]) -> list[bool]: ...


class PlanningProjection:
    def __init__(self) -> None:
        self.latest: PlanningSnapshotPublished | None = None
        self._history: list[str] = []
        self._latest_receipt: EventReceipt | None = None
        self.receipts: dict[tuple[str, str], EventReceipt] = {}
        self._snapshots: dict[str, str] = {}
        self.outcomes = {outcome.value: 0 for outcome in RevisionOutcome}

    def history_events(self) -> list[PlanningSnapshotPublished]:
        """Decode and validate all retained envelopes into detached views.

        Every call costs O(total retained payload size); call once outside loops.
        """
        return [PlanningSnapshotPublished.model_validate_json(wire) for wire in self._history]

    def snapshot_states(self) -> dict[str, PlanningSnapshot]:
        """Decode and validate every indexed snapshot into detached state.

        Every call costs O(total indexed payload size); call once outside loops.
        """
        return {
            identity: PlanningSnapshotPublished.model_validate_json(wire).data.state
            for identity, wire in self._snapshots.items()
        }

    def consume(self, event: PlanningSnapshotPublished) -> RevisionOutcome:
        receipt = EventReceipt.from_event(event)
        outcome = compare_revision(
            receipt,
            self._latest_receipt,
            prior_receipt=self.receipts.get((event.source, event.id)),
        )
        prior_wire = self._snapshots.get(event.data.state.snapshot_id)
        if prior_wire is not None:
            prior_state = json.loads(prior_wire)["data"]["state"]
            if prior_state != event.data.state.model_dump(mode="json"):
                outcome = RevisionOutcome.CONFLICT
        if outcome == RevisionOutcome.APPLY and self.latest:
            before, after = self.latest.data.state, event.data.state
            if before.as_of is not None and (
                after.as_of is None
                or after.as_of < before.as_of
                or (after.as_of == before.as_of and after != before)
            ):
                outcome = RevisionOutcome.CONFLICT
        self.outcomes[outcome.value] += 1
        if outcome == RevisionOutcome.APPLY:
            self.latest = event
            self._latest_receipt = receipt
            # Deep-copying a candidate retains these immutable strings instead of
            # recursively copying every historical record and its optional extras.
            wire = event.model_dump_json()
            self._history.append(wire)
            self._snapshots[event.data.state.snapshot_id] = wire
        if outcome != RevisionOutcome.CONFLICT:
            self.receipts[(event.source, event.id)] = receipt
        return outcome

    def profile(self, area: dict[str, Any], spatial: PlanningMembership) -> dict[str, Any]:
        if self.latest is None:
            return {"records": [], "unlocated_records": [], "removed_records": [], "snapshots": []}
        current = {r.development_key: r for r in self.latest.data.state.records}
        removed = {}
        # These envelopes were validated at acceptance. Decode plain
        # values once; rebuild typed records only when the removed-record view needs them.
        history = [json.loads(wire) for wire in self._history]
        for previous in history[:-1]:
            snapshot = previous["data"]["state"]
            for record in snapshot["records"]:
                if record["development_key"] not in current:
                    removed[record["development_key"]] = (record, source_time(snapshot["as_of"]))
        candidates = [
            *current.values(),
            *(PlanningRecord.model_validate(item[0]) for item in removed.values()),
        ]
        located = [record for record in candidates if record.position is not None]
        membership = (
            spatial.covers(
                area, [(r.position.longitude, r.position.latitude) for r in located if r.position]
            )
            if located
            else []
        )
        if len(membership) != len(located):
            raise ValueError("planning spatial adapter returned incomplete membership")
        inside = {r.development_key: member for r, member in zip(located, membership, strict=True)}
        records, unlocated, removed_records = [], [], []
        for record in candidates:
            member = inside.get(record.development_key)
            view = {**record.model_dump(mode="json"), "applicable": member}
            if record.development_key in removed:
                if member is not False:
                    removed_records.append(
                        {**view, "last_seen_as_of": removed[record.development_key][1]}
                    )
            elif member is None:
                unlocated.append(view)
            elif member:
                records.append(view)
        return {
            "records": sorted(records, key=lambda r: r["development_key"]),
            "unlocated_records": sorted(unlocated, key=lambda r: r["development_key"]),
            "removed_records": sorted(removed_records, key=lambda r: r["development_key"]),
            "snapshots": [
                {
                    "id": item["data"]["state"]["snapshot_id"],
                    "as_of": source_time(item["data"]["state"]["as_of"]),
                    "event_id": item["id"],
                }
                for item in history
            ],
        }

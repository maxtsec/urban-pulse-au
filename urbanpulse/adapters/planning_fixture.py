"""Normalize synthetic DAM-shaped snapshots without fetching a live provider."""

from typing import Any

from urbanpulse.contracts.planning import PLANNING_SCOPE, PlanningSnapshotPublished


class FixturePlanningNormalizer:
    def snapshot(self, raw: dict[str, Any], frame: dict[str, Any]) -> PlanningSnapshotPublished:
        return PlanningSnapshotPublished.model_validate(
            {
                "specversion": "1.0",
                "id": raw["event_id"],
                "source": "urn:urbanpulse:fixture:planning",
                "type": "au.urbanpulse.planning.snapshot-published.v1",
                "subject": PLANNING_SCOPE,
                "time": frame["received_at"],
                "datacontenttype": "application/json",
                "upmode": "fixture",
                "data": {
                    "schema_version": "1.0",
                    "revision": raw["revision"],
                    "provenance": {
                        "provider": "city-of-melbourne",
                        "product": "development-activity-monitor",
                        "record_id": "synthetic-pilot",
                        "capture_ids": [frame["id"]],
                        "source_observed_at": raw["as_of"],
                    },
                    "effective_from": None,
                    "effective_until": None,
                    "correlation_id": "synthetic-city-planning",
                    "causation_id": None,
                    "state": {
                        "scope_id": PLANNING_SCOPE,
                        "snapshot_id": raw["snapshot_id"],
                        "as_of": raw["as_of"],
                        "complete": raw["complete"],
                        "records": raw["records"],
                    },
                },
            }
        )

"""Retained planning history remains exact and rollback-safe after cheaper copies."""

from copy import deepcopy

import pytest

from urbanpulse.adapters.city_fixture import LocalCityCapture, capture_city
from urbanpulse.adapters.planning_fixture import FixturePlanningNormalizer
from urbanpulse.application.delivery import ProjectionHandler, RetryableHandlerError
from urbanpulse.contracts.planning import PlanningSnapshotPublished
from urbanpulse.location.planning import PlanningProjection


@pytest.fixture
def events(tmp_path):
    captured = LocalCityCapture(tmp_path, capture_city(tmp_path)).read()
    normalizer = FixturePlanningNormalizer()
    result = []
    for payload, frame in [("initial", 0), ("updated", 4)]:
        raw = deepcopy(captured.planning["payloads"][payload])
        raw["records"][0]["audit"] = {"notes": ["original"], "value": 1}
        result.append(normalizer.snapshot(raw, captured.planning["frames"][frame]))
    return result


def observable(state):
    return {
        "latest": state.latest.model_dump(mode="json") if state.latest else None,
        "history": [item.model_dump(mode="json") for item in state.history],
        "snapshots": {key: value.model_dump(mode="json") for key, value in state.snapshots.items()},
        "receipts": dict(state.receipts),
        "outcomes": dict(state.outcomes),
    }


def test_failed_candidate_cannot_change_nested_extras_history_or_receipts(events):
    initial, updated = events[:2]
    projection = PlanningProjection()
    projection.consume(initial)
    before = observable(projection)

    def fail(candidate, incoming):
        candidate.latest.data.state.records[0].model_extra["audit"]["notes"].append("changed")
        candidate.history[0].data.state.records[0].model_extra["audit"]["notes"].append("history")
        candidate.snapshots[initial.data.state.snapshot_id].records[0].model_extra["audit"][
            "notes"
        ].append("snapshot")
        candidate.consume(incoming)
        raise RetryableHandlerError("after candidate mutation")

    handler = ProjectionHandler(
        "planning", projection, PlanningSnapshotPublished.model_validate_json, fail
    )
    for _ in range(3):
        with pytest.raises(RetryableHandlerError):
            handler.handle(updated.model_dump_json())
        assert handler.state is projection
        assert observable(projection) == before
    handler.apply = PlanningProjection.consume
    assert handler.handle(updated.model_dump_json()).outcome == "applied"
    assert handler.state.outcomes["apply"] == 2
    assert len(handler.state.history) == len(handler.state.receipts) == 2
    assert observable(projection) == before


def test_copy_and_detached_history_views_do_not_share_mutable_extras(events):
    projection = PlanningProjection()
    for incoming in events[:2]:
        projection.consume(incoming)
    before = observable(projection)
    cloned = deepcopy(projection)
    cloned.latest.data.state.records[0].model_extra["audit"]["notes"].append("copy")
    cloned.history[0].data.state.records[0].model_extra["audit"]["notes"].append("view")
    cloned.snapshots[events[0].data.state.snapshot_id].records[0].model_extra["audit"][
        "notes"
    ].append("view")
    cloned.receipts.clear()
    cloned.outcomes["apply"] = 99
    assert observable(projection) == before
    assert projection.history[0].model_dump(mode="json") == events[0].model_dump(mode="json")


def test_snapshot_reuse_preserves_json_numeric_equivalence_and_detects_change(events):
    initial = events[0]
    projection = PlanningProjection()
    assert projection.consume(initial) == "apply"
    wire = initial.model_dump(mode="json")
    wire["data"]["state"]["records"][0]["audit"]["value"] = 1.0
    assert projection.consume(PlanningSnapshotPublished.model_validate(wire)) == "duplicate"
    wire["id"] = "another-event"
    wire["data"]["revision"] += 1
    wire["data"]["state"]["records"][0]["audit"]["notes"].append("changed")
    assert projection.consume(PlanningSnapshotPublished.model_validate(wire)) == "conflict"
    assert len(projection.history) == 1


def test_python_tuple_extra_retries_keep_the_same_wire_meaning(events):
    wire = events[0].model_dump(mode="json")
    wire["data"]["state"]["optional"] = (1, 2)
    incoming = PlanningSnapshotPublished.model_validate(wire)
    projection = PlanningProjection()
    assert projection.consume(incoming) == "apply"
    assert projection.consume(incoming) == "duplicate"
    assert (
        projection.consume(
            PlanningSnapshotPublished.model_validate_json(incoming.model_dump_json())
        )
        == "duplicate"
    )


def test_profile_removal_preserves_nested_optional_fields(events):
    initial, updated = events[:2]
    projection = PlanningProjection()
    projection.consume(initial)
    wire = updated.model_dump(mode="json")
    removed = initial.data.state.records[0].development_key
    wire["data"]["state"]["records"] = [
        item for item in wire["data"]["state"]["records"] if item["development_key"] != removed
    ]
    projection.consume(PlanningSnapshotPublished.model_validate(wire))

    class Spatial:
        def covers(self, area, points):
            return [True] * len(points)

    profile = projection.profile({}, Spatial())
    record = next(item for item in profile["removed_records"] if item["development_key"] == removed)
    assert record["audit"] == {"notes": ["original"], "value": 1}
    assert record["last_seen_as_of"] == initial.data.state.as_of
    record["audit"]["notes"].append("view changed")
    again = projection.profile({}, Spatial())
    record = next(item for item in again["removed_records"] if item["development_key"] == removed)
    assert record["audit"]["notes"] == ["original"]

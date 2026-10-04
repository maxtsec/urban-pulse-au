import json
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from urbanpulse.contracts.events import (
    EventReceipt,
    RevisionOutcome,
    VehiclePositionChanged,
    compare_revision,
)

FIXTURE = Path(__file__).parents[1] / "fixtures/vehicle-position-event.json"


def payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def receipt():
    return EventReceipt.from_event(VehiclePositionChanged.model_validate(payload()))


def test_serialization_preserves_unknown_time_and_optional_additions():
    data = payload()
    data["data"]["schema_version"] = "1.1"
    data["data"]["state"]["observed_at"] = None
    data["data"]["provenance"]["source_observed_at"] = None
    data["data"]["state"]["optional_label"] = "Synthetic tram"
    data["traceparent"] = "00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01"
    event = VehiclePositionChanged.model_validate(data)
    restored = VehiclePositionChanged.model_validate_json(event.model_dump_json())
    assert restored.model_dump(mode="json") == data
    assert restored.data.state.observed_at is None


def test_offset_timestamps_normalize_to_utc_without_changing_identity():
    data = payload()
    data["time"] = "2026-10-04T11:00:30+11:00"
    assert EventReceipt.from_event(VehiclePositionChanged.model_validate(data)) == receipt()


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("specversion",), "2.0"),
        (("type",), "au.urbanpulse.transport.vehicle-position-changed.v2"),
        (("source",), "urn:urbanpulse:live:transport"),
        (("source",), "urn:urbanpulse:fixture:weather"),
        (("time",), "2026-10-04T00:00:30"),
        (("time",), 1791072030),
        (("time",), "2026-10-04 00:00:30Z"),
        (("id",), ""),
        (("data", "revision"), 0),
        (("data", "revision"), True),
        (("data", "schema_version"), "2.0"),
        (("data", "provenance", "capture_ids"), []),
        (("data", "state", "position", "latitude"), 91),
        (("data", "state", "position", "longitude"), -181),
        (("data", "state", "position", "longitude"), True),
        (("data", "state", "position", "longitude"), float("nan")),
        (("data", "state", "observed_at"), "2026-10-04T00:01:00Z"),
        (("data", "effective_until"), "2026-10-04T00:00:20Z"),
        (("invalid_extension",), "value"),
        (("extension",), {"nested": "not a scalar"}),
    ],
)
def test_invalid_wire_contract_is_rejected(path, value):
    data = payload()
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValidationError):
        VehiclePositionChanged.model_validate(data)


def test_missing_required_provenance_is_rejected():
    data = payload()
    del data["data"]["provenance"]
    with pytest.raises(ValidationError):
        VehiclePositionChanged.model_validate(data)


def test_reusing_an_event_id_with_changed_content_is_a_conflict():
    data = payload()
    event = VehiclePositionChanged.model_validate(data)
    saved = EventReceipt.from_event(event)
    changed = payload()
    changed["data"]["state"]["position"]["longitude"] = 144.97
    other = EventReceipt.from_event(VehiclePositionChanged.model_validate(changed))
    assert saved == receipt()
    assert compare_revision(other, saved) == RevisionOutcome.CONFLICT


def test_new_revision_applies_and_old_revision_cannot_replace_it():
    current = receipt()
    newer = replace(current, event_id="new-event", revision=3, fingerprint="new-state")
    assert compare_revision(current, None) == RevisionOutcome.APPLY
    assert compare_revision(newer, current) == RevisionOutcome.APPLY
    assert compare_revision(current, newer) == RevisionOutcome.SUPERSEDED


def test_duplicate_and_equal_revision_conflicts_are_distinct():
    current = receipt()
    assert compare_revision(receipt(), current) == RevisionOutcome.DUPLICATE
    assert (
        compare_revision(replace(current, event_id="different-event"), current)
        == RevisionOutcome.CONFLICT
    )
    assert compare_revision(replace(current, revision=3), current) == RevisionOutcome.CONFLICT


@pytest.mark.parametrize("field", ["source", "subject"])
def test_different_scopes_cannot_share_an_ordering_cursor(field):
    current = receipt()
    with pytest.raises(ValueError, match="different producer/aggregate"):
        compare_revision(replace(current, **{field: "other"}), current)


def test_documented_event_matches_executable_fixture():
    document = (FIXTURE.parents[2] / "docs/architecture/capture-event-contract.md").read_text(
        encoding="utf-8"
    )
    example = document.split("```json\n", 1)[1].split("```", 1)[0]
    assert json.loads(example) == payload()
    assert VehiclePositionChanged.model_validate_json(example).id == receipt().event_id

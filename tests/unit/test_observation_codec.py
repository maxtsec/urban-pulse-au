"""Only declared event slots are interpreted, regardless of ordinary JSON key names."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from urbanpulse.adapters.observation_codec import decode_observation, encode_observation
from urbanpulse.contracts.events import VehiclePositionChanged


@pytest.fixture
def event():
    return VehiclePositionChanged.model_validate_json(
        (Path(__file__).parents[1] / "fixtures/vehicle-position-event.json").read_text()
    )


@pytest.mark.parametrize("owner", ["transport", "weather", "planning"])
def test_literal_reference_fields_are_never_interpreted(owner, event):
    opaque = {
        "event_reference": [event.source, event.id],
        "rejected_event": "ordinary data",
        "nested": [
            {"kind": "reference", "source": event.source, "id": event.id},
            {"rejected_event": "not JSON"},
        ],
    }
    slot = "events" if owner == "weather" else "event"
    row = {"frame": opaque, "evidence": opaque, slot: [event] if owner == "weather" else event}
    if owner == "weather":
        row["warning_records"] = []
    descriptor = {"kind": "reference", "source": event.source, "id": event.id}
    reference, resolve = Mock(return_value=descriptor), Mock(return_value=event)
    stored = json.loads(json.dumps(encode_observation(owner, row, reference)))
    restored = decode_observation(owner, 2, stored, resolve)
    assert restored == row
    assert restored["frame"] == opaque
    reference.assert_called_once_with(event)
    resolve.assert_called_once_with(descriptor)


@pytest.mark.parametrize("version", [1, 3, None, "2", True])
def test_unknown_version_is_rejected_before_resolving(version):
    resolve = Mock()
    with pytest.raises(ValueError, match="unsupported observation codec"):
        decode_observation("planning", version, {"event": None}, resolve)
    resolve.assert_not_called()


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {},
        {"event_reference": ["a", "b"]},
        {"kind": "reference", "source": [], "id": "x"},
        {"kind": "reference", "source": "a", "id": "b", "extra": True},
        {"kind": "reference", "source": "a", "id": "b", "attempt_envelope": {}},
        {"kind": "rejected", "envelope": None},
    ],
)
def test_invalid_list_event_descriptor_is_rejected(value):
    with pytest.raises(ValueError):
        decode_observation("weather", 2, {"events": [value]}, Mock())


def test_non_event_in_declared_write_slot_is_rejected():
    with pytest.raises(ValueError, match="validated event"):
        encode_observation("planning", {"event": {"kind": "reference"}}, Mock())


@pytest.mark.parametrize("row", [None, [], {}, {"events": None}, {"events": {}}])
def test_invalid_observation_structure_is_rejected(row):
    with pytest.raises(ValueError):
        decode_observation("weather", 2, row, Mock())


def test_null_single_event_and_empty_list_preserve_rejected_capture_metadata():
    for owner, row in [
        ("transport", {"event": None, "rejected_header": {"id": "invalid"}}),
        ("weather", {"events": [], "warning_records": [], "evidence": {"rejected": True}}),
    ]:
        resolve = Mock()
        assert decode_observation(owner, 2, row, resolve) == row
        resolve.assert_not_called()

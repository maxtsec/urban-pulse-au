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
    data["data"]["effective_from"] = None
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


@pytest.mark.parametrize(
    "context",
    [
        {},
        {"traceparent": "00-cccccccccccccccccccccccccccccccc-dddddddddddddddd-01"},
        {
            "traceparent": "00-cccccccccccccccccccccccccccccccc-dddddddddddddddd-01",
            "tracestate": "collector=retry",
        },
    ],
)
def test_redelivery_with_changed_or_removed_trace_context_is_duplicate(context):
    original = payload()
    original["traceparent"] = "00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01"
    original["tracestate"] = "collector=first"
    current = EventReceipt.from_event(VehiclePositionChanged.model_validate(original))
    retried = VehiclePositionChanged.model_validate({**payload(), **context})
    assert compare_revision(EventReceipt.from_event(retried), current) == RevisionOutcome.DUPLICATE
    wire = json.loads(retried.model_dump_json())
    for key, value in context.items():
        assert wire[key] == value


@pytest.mark.parametrize("path", [("semanticversion",), ("data", "state", "traceparent")])
def test_non_transport_extensions_still_participate_in_identity(path):
    original = payload()
    changed = payload()
    for data, value in ((original, "first"), (changed, "changed")):
        target = data
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
    current = EventReceipt.from_event(VehiclePositionChanged.model_validate(original))
    incoming = EventReceipt.from_event(VehiclePositionChanged.model_validate(changed))
    assert compare_revision(incoming, current) == RevisionOutcome.CONFLICT


@pytest.mark.parametrize(
    "path",
    [("data",), ("data", "provenance"), ("data", "state"), ("data", "state", "position")],
)
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_numbers_in_nested_extras_are_rejected(path, value):
    data = payload()
    target = data
    for key in path:
        target = target[key]
    target["optional_metrics"] = {"samples": [1.0, {"value": value}]}
    with pytest.raises(ValidationError, match="finite"):
        VehiclePositionChanged.model_validate(data)
    with pytest.raises(ValidationError, match="finite"):
        VehiclePositionChanged.model_validate_json(json.dumps(data))


def test_finite_nested_extras_preserve_numbers_and_explicit_null():
    data = payload()
    data["data"]["state"]["optional_metrics"] = {"samples": [0, -1.5, None, {"valid": True}]}
    event = VehiclePositionChanged.model_validate(data)
    assert json.loads(event.model_dump_json()) == data


@pytest.mark.parametrize("field", ["subject", "vehicle_id"])
def test_position_cannot_target_a_different_vehicle(field):
    data = payload()
    target = data if field == "subject" else data["data"]["state"]
    target[field] = "yarra-trams/another-vehicle"
    with pytest.raises(ValidationError, match="subject must match"):
        VehiclePositionChanged.model_validate(data)


def test_source_scoped_vehicle_identity_is_shared_by_payload_and_subject():
    data = payload()
    data["subject"] = data["data"]["state"]["vehicle_id"] = "another-provider/vehicle-1"
    event = VehiclePositionChanged.model_validate(data)
    assert event.subject == event.data.state.vehicle_id
    assert EventReceipt.from_event(event).subject == "another-provider/vehicle-1"


@pytest.mark.parametrize(("original", "retried"), [(1, 1.0), (0, -0.0), (10**20, 1e20)])
def test_equal_nested_json_numbers_have_duplicate_identity(original, retried):
    events = []
    for value in (original, retried):
        data = payload()
        data["data"]["state"]["metrics"] = {"nested": [value, {"value": value}]}
        events.append(
            EventReceipt.from_event(VehiclePositionChanged.model_validate_json(json.dumps(data)))
        )
    assert compare_revision(events[1], events[0]) == RevisionOutcome.DUPLICATE


@pytest.mark.parametrize(
    ("original", "changed"), [(1, True), (1, "1"), (1, 1.01), (2**53, 2**53 + 1)]
)
def test_numeric_normalization_does_not_hide_changed_values_or_types(original, changed):
    events = []
    for value in (original, changed):
        data = payload()
        data["data"]["state"]["metric"] = value
        events.append(EventReceipt.from_event(VehiclePositionChanged.model_validate(data)))
    assert compare_revision(events[1], events[0]) == RevisionOutcome.CONFLICT


def test_old_event_id_lookup_detects_changed_content_before_revision_ordering():
    original = receipt()
    latest = replace(original, event_id="new-event", revision=3, fingerprint="new-state")
    assert compare_revision(original, latest, prior_receipt=original) == RevisionOutcome.DUPLICATE
    for changed in (
        replace(original, fingerprint="tampered"),
        replace(original, revision=4),
        replace(original, subject="other-vehicle"),
    ):
        assert compare_revision(changed, latest, prior_receipt=original) == RevisionOutcome.CONFLICT
        assert compare_revision(changed, None, prior_receipt=original) == RevisionOutcome.CONFLICT
    # Without retained history, only ordering (not old event identity) is knowable.
    assert compare_revision(original, latest) == RevisionOutcome.SUPERSEDED


@pytest.mark.parametrize("field", ["source", "event_id"])
def test_prior_receipt_from_wrong_lookup_key_is_rejected(field):
    original = receipt()
    unrelated = replace(original, **{field: "unrelated"})
    with pytest.raises(ValueError, match="source/event ID"):
        compare_revision(original, None, prior_receipt=unrelated)


@pytest.mark.parametrize(
    "value", [-(2**31), 2**31 - 1, True, False, "", "https://example.org", "YmluYXJ5"]
)
def test_extension_primary_json_types_roundtrip(value):
    data = payload()
    data["extension"] = value
    event = VehiclePositionChanged.model_validate_json(json.dumps(data))
    assert json.loads(event.model_dump_json())["extension"] == value


@pytest.mark.parametrize(
    "value",
    [
        -(2**31) - 1,
        2**31,
        1.0,
        1.5,
        [],
        {},
        "line\nfeed",
        "\x7f",
        "\x9f",
        "\ufdd0",
        "\uffff",
        "\U0001fffe",
        "\ud800",
    ],
)
def test_invalid_extension_context_values_are_rejected(value):
    data = {**payload(), "extension": value}
    with pytest.raises(ValidationError, match="CloudEvents"):
        VehiclePositionChanged.model_validate(data)
    with pytest.raises(ValidationError):
        VehiclePositionChanged.model_validate_json(json.dumps(data))


def test_null_extension_is_unset_but_payload_null_is_preserved():
    event = VehiclePositionChanged.model_validate({**payload(), "extension": None})
    assert "extension" not in json.loads(event.model_dump_json())
    assert compare_revision(EventReceipt.from_event(event), receipt()) == RevisionOutcome.DUPLICATE
    assert event.data.causation_id is None


@pytest.mark.parametrize("value", ["Tram \U0001f68b", "\ud83d\ude8b"])
def test_extension_allows_unicode_and_valid_surrogate_pairs(value):
    event = VehiclePositionChanged.model_validate({**payload(), "extension": value})
    assert json.loads(event.model_dump_json())["extension"].endswith("\U0001f68b")


@pytest.mark.parametrize("effective_from", [None, "2026-10-04T00:00:24Z", "2026-10-04T00:00:26Z"])
def test_position_validity_cannot_invent_an_observation_time(effective_from):
    data = payload()
    data["data"]["effective_from"] = effective_from
    with pytest.raises(ValidationError, match="effective_from must equal observed_at"):
        VehiclePositionChanged.model_validate(data)


def test_unknown_position_observation_requires_unknown_effective_start():
    data = payload()
    data["data"]["state"]["observed_at"] = None
    data["data"]["provenance"]["source_observed_at"] = None
    with pytest.raises(ValidationError, match="effective_from must equal observed_at"):
        VehiclePositionChanged.model_validate(data)
    data["data"]["effective_from"] = None
    assert VehiclePositionChanged.model_validate(data).data.effective_from is None


def test_repeated_capture_references_are_rejected():
    data = payload()
    data["data"]["provenance"]["capture_ids"] *= 2
    with pytest.raises(ValidationError, match="capture_ids must be unique"):
        VehiclePositionChanged.model_validate(data)
    data["data"]["provenance"]["capture_ids"] = ["capture-1", "capture-2"]
    assert VehiclePositionChanged.model_validate(data).data.provenance.capture_ids == (
        "capture-1",
        "capture-2",
    )


@pytest.mark.parametrize("field", ["id", "subject"])
@pytest.mark.parametrize("character", ["\x00", "\x7f", "\x9f", "\ufdd0", "\ufffe", "\U0001ffff"])
def test_core_context_identifiers_reject_disallowed_characters(field, character):
    data = payload()
    data[field] += character
    if field == "subject":
        data["data"]["state"]["vehicle_id"] = data[field]
    with pytest.raises(ValidationError, match="controls or noncharacters|noncharacters"):
        VehiclePositionChanged.model_validate(data)
    with pytest.raises(ValidationError):
        VehiclePositionChanged.model_validate_json(json.dumps(data))


@pytest.mark.parametrize(
    "path", [("data",), ("data", "state"), ("data", "provenance"), ("data", "state", "position")]
)
@pytest.mark.parametrize("surrogate", ["\ud800", "\udfff"])
@pytest.mark.parametrize("location", ["value", "key"])
def test_python_payload_rejects_unpaired_surrogates_before_acceptance(path, surrogate, location):
    data = payload()
    target = data
    for part in path:
        target = target[part]
    target["optional"] = {
        "values": ("safe", {surrogate: "text"} if location == "key" else {"label": surrogate})
    }
    with pytest.raises(ValidationError, match="unpaired surrogates"):
        VehiclePositionChanged(**data)
    with pytest.raises(ValidationError):
        VehiclePositionChanged.model_validate_json(json.dumps(data))


def test_payload_unicode_pairs_roundtrip_without_restricting_json_text():
    data = payload()
    data["id"] = "event-\ud83d\ude8b"
    data["data"]["state"]["optional"] = {
        "\ud83d\ude8b": ["\ud83d\ude8b", "line\ntext\x00\x7f\ufdd0"]
    }
    event = VehiclePositionChanged(**data)
    wire = event.model_dump_json()
    restored = VehiclePositionChanged.model_validate_json(wire)
    assert event.id == "event-\U0001f68b"
    assert restored.data.state.model_extra["optional"] == {
        "\U0001f68b": ["\U0001f68b", "line\ntext\x00\x7f\ufdd0"]
    }
    assert EventReceipt.from_event(event) == EventReceipt.from_event(restored)


def test_normalizing_payload_keys_cannot_silently_overwrite_content():
    data = payload()
    data["data"]["state"]["optional"] = {"\ud83d\ude8b": 1, "\U0001f68b": 2}
    with pytest.raises(ValidationError, match="keys must be unique"):
        VehiclePositionChanged.model_validate(data)


@pytest.mark.parametrize("observed", [None, "2026-10-04T00:00:25Z"])
def test_position_producer_cannot_extend_freshness_with_effective_until(observed):
    data = payload()
    data["data"]["effective_from"] = observed
    data["data"]["state"]["observed_at"] = observed
    data["data"]["provenance"]["source_observed_at"] = observed
    data["data"]["effective_until"] = "2099-01-01T00:00:00Z"
    with pytest.raises(ValidationError, match="position effective_until must be null"):
        VehiclePositionChanged.model_validate(data)
    data["data"]["effective_until"] = None
    assert VehiclePositionChanged.model_validate(data).data.effective_until is None

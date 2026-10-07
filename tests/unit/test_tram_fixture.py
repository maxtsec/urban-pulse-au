"""Compatible trip metadata and independently reproducible static geometry."""

import copy
import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts.build_tram_fixture import components, encoded, ordered_shapes
from urbanpulse.contracts.events import EventReceipt, VehiclePositionChanged

FIXTURES = Path(__file__).parents[1] / "fixtures"
MAP = FIXTURES / "map02"


def original():
    return json.loads((FIXTURES / "vehicle-position-event.json").read_text(encoding="utf-8"))


def test_legacy_wires_and_receipts_match_prechange_golden_hashes():
    expected = [
        (
            "vehicle-position-event.json",
            1,
            "f771bf382477d8951f3400e1dbe74c69ab8f4adf5a39ef4675a1f206a25a4bbf",
            "253eb3a16510cca94583340b9bdff0211551acd9be45eeec46aaeb0d4e83afef",
        ),
        (
            "city-scenario.json",
            8,
            "6f7ec0adacda0948aa1f9236a582c6070b02727d7f6b77ee25dcff453c8adc89",
            "395041bab24fc35374141c2b1c25877865d510311cbc1145ac4d5907c6b4c784",
        ),
    ]
    for name, count, wire_hash, receipt_hash in expected:
        source = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
        payloads = [source] if "frames" not in source else [f["event"] for f in source["frames"]]
        events = []
        for payload in payloads:
            try:
                events.append(VehiclePositionChanged.model_validate(payload))
            except ValidationError:
                pass  # The retained city fixture deliberately contains one rejected latitude.
        assert len(events) == count
        wires = [e.model_dump(mode="json") for e in events]
        receipts = [EventReceipt.from_event(e).fingerprint for e in events]
        assert (
            hashlib.sha256(
                json.dumps(wires, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            == wire_hash
        )
        assert (
            hashlib.sha256(json.dumps(receipts, separators=(",", ":")).encode()).hexdigest()
            == receipt_hash
        )
        for event in events:
            assert "trip" not in event.data.state.model_dump()
            restored = VehiclePositionChanged.model_validate_json(event.model_dump_json())
            assert EventReceipt.from_event(restored) == EventReceipt.from_event(event)


def test_explicit_null_trip_remains_explicit_and_unknown_extras_survive():
    payload = original()
    payload["data"]["state"]["trip"] = None
    event = VehiclePositionChanged.model_validate(payload)
    assert event.model_dump(mode="json") == payload
    payload["data"]["state"]["trip"] = {"trip_id": "trip-a", "optional_source_field": "kept"}
    event = VehiclePositionChanged.model_validate(payload)
    assert event.data.state.trip.model_extra["optional_source_field"] == "kept"
    assert event.data.state.trip.service_date is None
    assert event.data.state.trip.direction_id is None


@pytest.mark.parametrize(
    "trip",
    [
        {"trip_id": ""},
        {"trip_id": "bad\x00"},
        {"service_date": "20260230"},
        {"service_date": "2026-10-07"},
        {"service_date": 20261007},
        {"start_time": "24:60:00"},
        {"start_time": "noon"},
        {"direction_id": True},
        {"direction_id": 2},
        {"direction_id": "0"},
    ],
)
def test_invalid_known_trip_fields_are_rejected(trip):
    payload = original()
    payload["data"]["state"]["trip"] = trip
    with pytest.raises(ValidationError):
        VehiclePositionChanged.model_validate(payload)


def test_trip_changes_are_part_of_event_identity_and_service_time_can_exceed_24_hours():
    payload = original()
    payload["data"]["state"]["trip"] = {
        "trip_id": "trip-a",
        "service_date": "20261007",
        "start_time": "25:03:00",
        "direction_id": 0,
    }
    before = VehiclePositionChanged.model_validate(payload)
    changed = copy.deepcopy(payload)
    changed["data"]["state"]["trip"]["trip_id"] = "trip-b"
    assert (
        EventReceipt.from_event(before).fingerprint
        != EventReceipt.from_event(VehiclePositionChanged.model_validate(changed)).fingerprint
    )
    assert VehiclePositionChanged.model_validate_json(before.model_dump_json()) == before


def test_committed_assets_match_manifest_and_fixture_trip_links():
    manifest = json.loads((MAP / "manifest.json").read_text(encoding="utf-8"))
    for name, description in manifest["artifacts"].items():
        raw = (MAP / name).read_bytes()
        assert len(raw) == description["bytes"]
        assert hashlib.sha256(raw).hexdigest() == description["sha256"]
        assert encoded(json.loads(raw)) == raw
    # Hash the committed LF representation, independent of a checkout's newline conversion.
    boundary = (FIXTURES / "southbank.geojson").read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(boundary).hexdigest() == manifest["boundary_sha256"]
    geo = json.loads((MAP / "southbank-tram-shapes.geojson").read_text())
    data = json.loads((MAP / "trip-observations.json").read_text())
    features = {f["properties"]["segment_id"]: f for f in geo["features"]}
    assert len(features) == manifest["segment_count"]
    assert (
        sorted({f["properties"]["shape_id"] for f in features.values()})
        == manifest["included_shape_ids"]
    )
    assert set(manifest["included_shape_ids"]).isdisjoint(manifest["excluded_shape_ids"])
    assert (
        len(manifest["included_shape_ids"]) + len(manifest["excluded_shape_ids"])
        == manifest["source_shape_count"]
    )
    links = {t["trip_id"]: t for t in data["static_trip_links"]}
    assert len(links) == 2
    for f in features.values():
        distances = f["properties"]["distances_m"]
        assert len(distances) == len(f["geometry"]["coordinates"])
        assert distances[0] >= 0 and all(
            b > a for a, b in zip(distances, distances[1:], strict=False)
        )
    events = [VehiclePositionChanged.model_validate(f["event"]) for f in data["frames"]]
    assert len(events) == 6
    assert all(e.upmode == "fixture" and e.data.provenance.provider == "synthetic" for e in events)
    for frame, event in zip(data["frames"], events, strict=True):
        trip = event.data.state.trip
        link = links[trip.trip_id]
        assert trip.service_date == link["service_date"] and trip.start_time == link["start_time"]
        assert trip.direction_id == int(link["direction_id"])
        assert event.data.state.route_id == link["route_id"]
        shape = features[link["segment_id"]]
        assert shape["properties"]["shape_id"] == link["shape_id"]
        assert link["route_id"] in shape["properties"]["route_ids"]
        assert [event.data.state.position.longitude, event.data.state.position.latitude] in shape[
            "geometry"
        ]["coordinates"]
        assert frame["at_seconds"] % 30 == 5
    assert events[2].data.state.trip.trip_id != events[3].data.state.trip.trip_id


def test_shape_vertex_order_is_numeric_and_duplicate_or_nonfinite_data_fails():
    rows = [
        {"shape_id": "s", "shape_pt_sequence": str(i), "shape_pt_lon": str(i), "shape_pt_lat": "0"}
        for i in (10, 2)
    ]
    assert ordered_shapes(rows)[0]["geometry"]["coordinates"] == [[2.0, 0.0], [10.0, 0.0]]
    with pytest.raises(ValueError, match="sequence"):
        ordered_shapes(rows + rows[:1])
    with pytest.raises(ValueError, match="coordinates"):
        ordered_shapes([{**rows[0], "shape_pt_lon": "nan"}, rows[1]])


def test_components_keep_original_offsets_and_do_not_bridge_excluded_distance():
    def line(a, b):
        return {"type": "LineString", "coordinates": [[a, 0], [b, 0]]}

    geo = components(
        [
            ("s", 1, 100.0, 110.0, line(0, 1)),
            ("s", 2, 110.0, 120.0, line(1, 2)),
            ("s", 2, 130.0, 140.0, line(3, 4)),
        ]
    )
    assert [f["properties"]["distances_m"] for f in geo["features"]] == [
        [100.0, 110.0, 120.0],
        [130.0, 140.0],
    ]
    assert [f["geometry"]["coordinates"] for f in geo["features"]] == [
        [[0, 0], [1, 0], [2, 0]],
        [[3, 0], [4, 0]],
    ]

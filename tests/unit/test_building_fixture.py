"""Static map data is independently versioned and cannot change domain fixtures."""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts.build_building_fixture import BOUNDARY, FIXTURE, MANIFEST, export_query, transform


def source():
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "structure_id": "tower",
                    "footprint_type": "Structure",
                    "footprint_min_elevation": 24.0,
                    "footprint_max_elevation": 104.0,
                    "structure_min_elevation": 4.0,
                    "date_captured": "20200515",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[144.96, -37.82], [144.961, -37.82], [144.961, -37.821], [144.96, -37.82]]
                    ],
                },
            }
        ],
    }


def test_stacked_component_uses_structure_base_not_ground_or_total_height():
    data, counts = transform(source())
    assert data["features"][0]["properties"] == {
        "structure_id": "tower",
        "footprint_type": "Structure",
        "base_m": 20.0,
        "top_m": 100.0,
        "date_captured": "2020-05-15",
    }
    assert counts["included_count"] == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("footprint_min_elevation", None),
        ("footprint_max_elevation", float("nan")),
        ("structure_min_elevation", float("inf")),
        ("footprint_min_elevation", 3),
        ("footprint_max_elevation", 24),
        ("footprint_max_elevation", True),
    ],
)
def test_invalid_elevation_is_counted_and_never_defaulted(field, value):
    data = source()
    data["features"][0]["properties"][field] = value
    fixture, counts = transform(data)
    assert fixture["features"] == []
    assert counts["rejected_structure_count"] == 1


def test_other_types_are_excluded_and_order_is_deterministic():
    data = source()
    other = copy.deepcopy(data["features"][0])
    other["properties"]["footprint_type"] = "Tram Stop"
    data["features"].append(other)
    a = transform(data)
    data["features"].reverse()
    assert transform(data) == a
    assert a[1]["excluded_by_type"] == {"Tram Stop": 1}


def test_rounded_geometry_preserves_holes_and_rejects_collapsed_rings():
    data = source()
    ring = data["features"][0]["geometry"]["coordinates"][0]
    data["features"][0]["geometry"]["coordinates"].append(copy.deepcopy(ring))
    assert len(transform(data)[0]["features"][0]["geometry"]["coordinates"]) == 2
    data["features"][0]["geometry"]["coordinates"] = [
        [[1.00000001, 1], [1.00000002, 1], [1, 1.00000001], [1.00000001, 1]]
    ]
    assert transform(data)[1]["rejected_structure_count"] == 1


def test_committed_buildings_match_manifest_boundary_and_approved_scope():
    manifest = json.loads(MANIFEST.read_text())
    raw = FIXTURE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == manifest["fixture_sha256"]
    assert hashlib.sha256(BOUNDARY.read_bytes()).hexdigest() == manifest["boundary_sha256"]
    assert manifest["export_query"] == {"where": export_query(json.loads(BOUNDARY.read_text()))}
    features = json.loads(raw)["features"]
    assert len(features) == manifest["counts"]["included_count"] == 1108
    assert manifest["counts"]["source_count"] == 1189
    assert manifest["counts"]["capture_dates"]["2020-05-15"] == 2
    assert manifest["fixture_bytes"] == len(raw)
    assert len({f["properties"]["structure_id"] for f in features}) == 320
    assert all(
        f["properties"]["footprint_type"] == "Structure"
        and 0 <= f["properties"]["base_m"] < f["properties"]["top_m"]
        for f in features
    )
    allowlist = (Path(__file__).resolve().parents[2] / "apps/web/.dockerignore").read_text()
    assert "!src/assets/southbank-buildings.geojson" in allowlist

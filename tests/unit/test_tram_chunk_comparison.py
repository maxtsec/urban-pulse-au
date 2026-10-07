"""A route experiment must include outside-area shapes, not only the pilot union."""

import copy
import json

import pytest

from scripts.build_tram_chunk_comparison import comparison, route_pool
from scripts.build_tram_shape_pool import INDEX, digest


@pytest.fixture
def inputs():
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    index["areas"] = {
        "a": {"name": "A", "boundary_sha256": "a" * 64, "shape_ids": ["shared"]},
        "b": {"name": "B", "boundary_sha256": "b" * 64, "shape_ids": ["other"]},
    }
    features = {}
    for identity, routes in (("shared", ["1", "2"]), ("other", ["2"]), ("outside", ["1"])):
        features[identity] = {
            "type": "Feature",
            "properties": {"shape_id": identity, "route_ids": routes},
            "geometry": {"type": "LineString", "coordinates": [[144.9, -37.8], [145, -37.8]]},
        }
    return index, features


def test_route_objects_include_outside_shapes_and_deduplicate_only_at_selection(inputs):
    index, features = inputs
    files, report = route_pool(index, features)
    area = report["areas"]["a"]
    manifest = json.loads(files[area["manifest"]["path"]])
    assert area["cold_requests"] == 3
    assert area["extra_shapes"] == 2
    assert manifest["shape_ids"] == ["shared"]
    assert set(manifest["objects"]) == {"1", "2"}
    for route, reference in manifest["objects"].items():
        raw = files[reference["path"]]
        assert digest(raw) == reference["sha256"] and len(raw) == reference["bytes"]
        obj = json.loads(raw)
        assert obj["route_id"] == route
        assert {f["properties"]["shape_id"] for f in obj["features"]} == {
            s for s, f in features.items() if route in f["properties"]["route_ids"]
        }
        assert "source_revision" not in obj
    assert area["cold_bytes"] == area["manifest"]["bytes"] + sum(
        r["bytes"] for r in manifest["objects"].values()
    )


def test_reordering_and_adding_area_preserves_route_objects_and_existing_manifests(inputs):
    index, features = inputs
    original = route_pool(index, features)
    index["areas"] = dict(reversed(list(index["areas"].items())))
    assert route_pool(index, dict(reversed(list(features.items())))) == original
    index["areas"]["c"] = {"name": "C", "boundary_sha256": "c" * 64, "shape_ids": ["outside"]}
    files, report = route_pool(index, features)
    assert all(files[k] == v for k, v in original[0].items())
    assert all(report["areas"][k] == v for k, v in original[1]["areas"].items())


def test_release_provenance_does_not_change_route_objects(inputs):
    index, features = inputs
    original, _ = route_pool(index, features)
    index["tram_archive_sha256"] = "c" * 64
    index["source_archive_sha256"] = "d" * 64
    changed, _ = route_pool(index, features)
    assert {k: v for k, v in original.items() if k.startswith("objects/")} == {
        k: v for k, v in changed.items() if k.startswith("objects/")
    }


def test_shape_without_route_fails_instead_of_understating_download(inputs):
    index, features = inputs
    features["shared"]["properties"]["route_ids"] = []
    with pytest.raises(ValueError, match="no route"):
        route_pool(index, features)


def test_comparison_refuses_geometry_drift_and_keeps_baseline_exact(inputs):
    index, features = inputs
    retained = {"shared": copy.deepcopy(features["shared"])}
    files, report = comparison(index, features, retained)
    assert report["complete_source_shapes"] == 3
    assert report["layouts"]["shape"]["a"]["cold_requests"] == 2
    assert report["layouts"]["route"]["a"]["extra_shapes"] == 2
    assert json.loads(files["comparison.json"]) == report
    retained["shared"]["geometry"]["coordinates"][0][0] += 0.1
    with pytest.raises(ValueError, match="differs from retained"):
        comparison(index, features, retained)

"""Shared route assets retain identity, integrity and independently selected scopes."""

import copy
import hashlib
import json

import pytest

from scripts.build_tram_area_fixture import OUTPUT, ROOT, additional_shapes
from scripts.build_tram_fixture import ARCHIVE_SHA256, encoded


def collection(*identities):
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"shape_id": i},
                "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
            }
            for i in identities
        ],
    }


def test_shared_routes_are_retained_once_without_mutating_either_scope():
    primary, secondary = collection("a", "shared"), collection("shared", "b")
    before = copy.deepcopy((primary, secondary))
    assert additional_shapes(primary, secondary) == collection("b")
    assert (primary, secondary) == before
    assert additional_shapes(primary, primary) == collection()


def test_shared_identity_with_different_content_is_rejected():
    primary, secondary = collection("shared"), collection("shared")
    secondary["features"][0]["geometry"]["coordinates"][1] = [2, 2]
    with pytest.raises(ValueError, match="Shared shape content differs"):
        additional_shapes(primary, secondary)


@pytest.mark.parametrize("duplicate_primary", [True, False])
def test_duplicate_identity_is_rejected_in_either_scope(duplicate_primary):
    first, second = collection("same", "same"), collection("other")
    if not duplicate_primary:
        first, second = second, first
    with pytest.raises(ValueError, match="Duplicate shape identity"):
        additional_shapes(first, second)


def test_committed_scope_indexes_resolve_once_and_match_all_artifact_hashes():
    index = json.loads((OUTPUT / "index.json").read_text(encoding="utf-8"))
    assert index["source_archive_sha256"] == ARCHIVE_SHA256
    by_id = {}
    for path, record in index["assets"].items():
        raw = (ROOT / path).read_bytes()
        assert len(raw) == record["bytes"]
        assert hashlib.sha256(raw).hexdigest() == record["sha256"]
        decoded = json.loads(raw)
        assert encoded(decoded) == raw
        assert (
            sorted(f["properties"]["shape_id"] for f in decoded["features"]) == record["shape_ids"]
        )
        for feature in decoded["features"]:
            identity = feature["properties"]["shape_id"]
            assert identity not in by_id
            by_id[identity] = feature
    for area in index["areas"].values():
        raw = (ROOT / area["boundary_path"]).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(raw).hexdigest() == area["boundary_sha256"]
        assert json.loads(raw)["properties"]["name"] == area["name"]
        selected = [by_id[i] for i in area["shape_ids"]]
        assert area["vertices"] == sum(len(f["geometry"]["coordinates"]) for f in selected)
        assert (
            len(encoded({"type": "FeatureCollection", "features": selected}))
            == area["standalone_geometry_bytes"]
        )
    primary = set(index["areas"]["southbank"]["shape_ids"])
    secondary = set(index["areas"]["melbourne-cbd"]["shape_ids"])
    assert sorted(primary & secondary) == index["shared_shape_ids"]
    assert len(primary | secondary) == index["unique_shape_count"] == len(by_id)
    assert len(secondary - primary) == index["additional_shape_count"]
    assert index["retained_geometry_bytes"] == sum(a["bytes"] for a in index["assets"].values())
    assert index["retained_geometry_bytes"] < index["separate_area_geometry_bytes"]

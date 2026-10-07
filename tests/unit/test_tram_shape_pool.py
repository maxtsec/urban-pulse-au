"""Area order and later additions cannot change an existing area's shape downloads."""

import copy
import json

import pytest

from scripts.build_tram_fixture import ROOT, encoded
from scripts.build_tram_shape_pool import (
    INDEX,
    build_pool,
    digest,
    load_inputs,
    main,
    publish,
    write_pool,
)


@pytest.fixture(scope="module")
def inputs():
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    return index, load_inputs(index, ROOT)


def manifest(files, report, area):
    reference = report["areas"][area]["manifest"]
    raw = files[reference["path"]]
    assert digest(raw) == reference["sha256"] and len(raw) == reference["bytes"]
    return json.loads(raw)


def test_reordering_areas_and_source_objects_preserves_every_byte(inputs):
    index, features = inputs
    reverse = copy.deepcopy(index)
    reverse["areas"] = dict(reversed(list(reverse["areas"].items())))
    for area in reverse["areas"].values():
        area["shape_ids"].reverse()
    assert build_pool(index, features) == build_pool(
        reverse, dict(reversed(list(features.items())))
    )


def test_cbd_alone_and_cbd_after_southbank_have_identical_required_objects(inputs):
    index, features = inputs
    files, report = build_pool(index, features)
    cbd_only = copy.deepcopy(index)
    cbd_only["areas"] = {"melbourne-cbd": cbd_only["areas"]["melbourne-cbd"]}
    own_files, own_report = build_pool(cbd_only, features)
    assert own_report["areas"]["melbourne-cbd"] == report["areas"]["melbourne-cbd"]
    own = manifest(own_files, own_report, "melbourne-cbd")
    assert own == manifest(files, report, "melbourne-cbd")
    assert set(own["shapes"]) == set(index["areas"]["melbourne-cbd"]["shape_ids"])
    southbank_only = set(index["areas"]["southbank"]["shape_ids"]) - set(own["shapes"])
    assert len(southbank_only) == 5
    assert len(own_files) == len(own["shapes"]) + 1
    assert all(files[name] == raw for name, raw in own_files.items())


def test_later_synthetic_third_area_cannot_rename_existing_manifests_or_objects(inputs):
    index, features = inputs
    before, summary = build_pool(index, features)
    expanded, expanded_features = copy.deepcopy(index), copy.deepcopy(features)
    shared = index["shared_shape_ids"][0]
    extra = copy.deepcopy(features[shared])
    extra["properties"]["shape_id"] = "synthetic-third-area-only"
    extra["properties"]["segment_id"] = "synthetic-third-area-only/full"
    expanded_features["synthetic-third-area-only"] = extra
    expanded["areas"]["synthetic-third-area"] = {
        "name": "Synthetic third area",
        "boundary_sha256": "0" * 64,
        "shape_ids": [shared, "synthetic-third-area-only"],
    }
    after, report = build_pool(expanded, expanded_features)
    assert all(after[name] == raw for name, raw in before.items())
    for area in index["areas"]:
        assert report["areas"][area] == summary["areas"][area]
    assert report["unique_objects"] == summary["unique_objects"] + 1


def test_manifests_resolve_exact_original_shapes_and_cold_warm_totals(inputs):
    index, features = inputs
    files, report = build_pool(index, features)
    assert encoded(report) == (INDEX.parent / "shape-pool-report.json").read_bytes()
    for area, record in report["areas"].items():
        data = manifest(files, report, area)
        total = record["manifest"]["bytes"]
        for identity, ref in data["shapes"].items():
            raw = files[ref["path"]]
            assert digest(raw) == ref["sha256"] and len(raw) == ref["bytes"]
            obj = json.loads(raw)
            assert obj["feature"] == features[identity]
            assert "source_revision" not in obj
            assert data["source_revision"] == index["tram_archive_sha256"]
            assert data["source"]["source_archive_sha256"] == index["source_archive_sha256"]
            total += len(raw)
        assert total == record["cold_bytes"]
        assert record["cold_requests"] == 1 + len(data["shapes"])
    southbank = manifest(files, report, "southbank")["shapes"]
    cbd = manifest(files, report, "melbourne-cbd")["shapes"]
    cached = {r["sha256"] for r in southbank.values()}
    uncached = [r for r in cbd.values() if r["sha256"] not in cached]
    assert len(uncached) == index["additional_shape_count"] == 163
    for identity in index["shared_shape_ids"]:
        assert southbank[identity] == cbd[identity]


@pytest.mark.parametrize("bad", ["missing", "duplicate", "wrong_identity"])
def test_bad_area_references_are_rejected(inputs, bad):
    index, features = copy.deepcopy(inputs)
    area = index["areas"]["southbank"]
    identity = area["shape_ids"][0]
    if bad == "missing":
        del features[identity]
    elif bad == "duplicate":
        area["shape_ids"].append(identity)
    else:
        features[identity]["properties"]["shape_id"] = "wrong"
    with pytest.raises(ValueError, match="shape reference"):
        build_pool(index, features)


@pytest.mark.parametrize("changed_member", [False, True])
def test_release_only_changes_reuse_every_shape_object(inputs, changed_member, tmp_path):
    index, features = inputs
    before, old_report = build_pool(index, features)
    changed = copy.deepcopy(index)
    changed["source_archive_sha256"] = "1" * 64
    changed["source_last_modified"] = "2026-10-08T00:00:00Z"
    if changed_member:
        changed["tram_archive_sha256"] = "2" * 64
    after, new_report = build_pool(changed, features)
    objects = {name: raw for name, raw in before.items() if name.startswith("objects/")}
    assert objects == {name: raw for name, raw in after.items() if name.startswith("objects/")}
    write_pool(tmp_path, before, old_report)
    mtimes = {name: (tmp_path / name).stat().st_mtime_ns for name in objects}
    write_pool(tmp_path, after, new_report)
    assert len(list((tmp_path / "objects").iterdir())) == len(objects) == 371
    assert mtimes == {name: (tmp_path / name).stat().st_mtime_ns for name in objects}
    for area in index["areas"]:
        prior, current = manifest(before, old_report, area), manifest(after, new_report, area)
        assert current["shapes"] == prior["shapes"]
        assert current["source_revision"] == changed["tram_archive_sha256"]
        assert current["source"] == {
            **prior["source"],
            **{
                k: changed[k]
                for k in ("source_archive_sha256", "tram_archive_sha256", "source_last_modified")
            },
        }
        assert new_report["areas"][area]["manifest"] != old_report["areas"][area]["manifest"]


def test_changed_shape_replaces_only_its_object(inputs):
    index, features = inputs
    before, old_report = build_pool(index, features)
    updated = copy.deepcopy(features)
    identity = index["shared_shape_ids"][0]
    updated[identity]["geometry"]["coordinates"][0][0] += 0.000001
    after, new_report = build_pool(index, updated)
    old_objects = {name for name in before if name.startswith("objects/")}
    new_objects = {name for name in after if name.startswith("objects/")}
    assert len(old_objects - new_objects) == len(new_objects - old_objects) == 1
    assert all(before[name] == after[name] for name in old_objects & new_objects)
    for area in index["areas"]:
        prior, current = manifest(before, old_report, area), manifest(after, new_report, area)
        changed = {key for key in prior["shapes"] if prior["shapes"][key] != current["shapes"][key]}
        assert changed == {identity}


@pytest.mark.parametrize(
    "kind", ["hash", "length", "missing", "escape", "release", "member", "boundary"]
)
def test_corrupt_or_untrusted_input_is_rejected_before_publication(inputs, kind):
    index, _ = copy.deepcopy(inputs)
    path = next(iter(index["assets"]))
    if kind == "hash":
        index["assets"][path]["sha256"] = "0" * 64
    elif kind == "length":
        index["assets"][path]["bytes"] += 1
    elif kind == "missing":
        index["assets"]["tests/fixtures/absent-shape-asset.json"] = index["assets"].pop(path)
    elif kind == "escape":
        index["assets"]["../outside.json"] = index["assets"].pop(path)
    elif kind == "release":
        index["source_archive_sha256"] = "0" * 64
    elif kind == "member":
        index["tram_archive_sha256"] = "0" * 64
    else:
        index["areas"]["southbank"]["boundary_sha256"] = "0" * 64
    with pytest.raises((ValueError, FileNotFoundError)):
        load_inputs(index, ROOT)


def test_repeat_build_preserves_files_and_refuses_corrupted_existing_object(inputs, tmp_path):
    files, report = build_pool(*inputs)
    reference = write_pool(tmp_path, files, report)
    before = {p.relative_to(tmp_path): p.stat().st_mtime_ns for p in tmp_path.rglob("*.json")}
    assert write_pool(tmp_path, files, report) == reference
    assert {
        p.relative_to(tmp_path): p.stat().st_mtime_ns for p in tmp_path.rglob("*.json")
    } == before
    assert (tmp_path / reference).read_bytes() == encoded(report)
    target = tmp_path / next(name for name in files if name.startswith("objects/"))
    target.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="Existing content-addressed file differs"):
        write_pool(tmp_path, files, report)
    assert target.read_bytes() == b"corrupt"


def test_failed_atomic_publication_leaves_no_final_file_or_temporary_file(tmp_path, monkeypatch):
    def fail_link(*args):
        raise OSError("simulated unsupported filesystem")

    monkeypatch.setattr("scripts.build_tram_shape_pool.os.link", fail_link)
    target = tmp_path / "objects" / "example.json"
    with pytest.raises(OSError, match="simulated"):
        publish(target, b"complete bytes")
    assert not target.exists()
    assert list(target.parent.iterdir()) == []


def test_cli_builds_a_resolvable_verified_pool_offline(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["build_tram_shape_pool", "--output", str(tmp_path)])
    main()
    result = json.loads(capsys.readouterr().out)
    report = json.loads((tmp_path / result["report"]).read_text(encoding="utf-8"))
    assert result["objects"] == report["unique_objects"] == 371
    for area in report["areas"].values():
        ref = area["manifest"]
        raw = (tmp_path / ref["path"]).read_bytes()
        assert digest(raw) == ref["sha256"]
        for obj in json.loads(raw)["shapes"].values():
            content = (tmp_path / obj["path"]).read_bytes()
            assert len(content) == obj["bytes"] and digest(content) == obj["sha256"]

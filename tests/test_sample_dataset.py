"""Offline sample contracts: pinned inputs, calendar selection and complete public output."""

import json
from datetime import date
from pathlib import Path

import pytest

from scripts.build_sample_dataset import DAY, along, build, service_ids, source_pack, time_ms

ROOT = Path(__file__).resolve().parents[1]


def test_calendar_exceptions_and_previous_service_day():
    row = dict(
        service_id="weekday",
        start_date="20261001",
        end_date="20261009",
        thursday="1",
        wednesday="1",
    )
    assert service_ids([row], [], DAY) == {"weekday"}
    assert service_ids(
        [row],
        [
            dict(service_id="weekday", date="20261008", exception_type="2"),
            dict(service_id="special", date="20261008", exception_type="1"),
        ],
        DAY,
    ) == {"special"}
    assert service_ids([row], [], date(2026, 10, 7)) == {"weekday"}
    assert time_ms("25:30:00") == 91_800_000
    with pytest.raises(ValueError):
        time_ms("12:60:00")


def test_distance_conversion_uses_shape_units_and_rejects_outside():
    assert along(150, [0, 100, 200], [0, 80, 180]) == 130
    assert along(200, [0, 100, 200], [0, 80, 180]) == 180
    for value in [-1, 201, float("nan")]:
        with pytest.raises(ValueError):
            along(value, [0, 100, 200], [0, 80, 180])


def test_changed_archive_is_rejected(tmp_path):
    path = tmp_path / "bad.zip"
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        source_pack(path, ROOT / "sample-data/sources.lock.json")


def test_committed_sample_rebuilds_byte_for_byte(tmp_path):
    manifest = build(
        ROOT / "sample-data/sources.zip", ROOT / "sample-data/sources.lock.json", tmp_path
    )
    for name in [*manifest["files"], "manifest.json"]:
        assert (tmp_path / name).read_bytes() == (
            ROOT / "apps/web/src/assets/sample" / name
        ).read_bytes()
    assert manifest["schedule_exclusions"] == {}
    city = json.loads((tmp_path / "city.json").read_bytes())
    assert len(city["schedule"]["trips"]) > 4000
    assert len(city["water"]["features"]) == 1
    assert city["water"]["features"][0]["properties"]["name"] == "YARRA RIVER"
    assert len(city["roads"]["features"]) > 1000
    assert len(city["developments"]) == 463
    assert any(t["service_date"] < "2026-10-08" for t in city["schedule"]["trips"])
    assert all(p["development_key"].startswith("X") for p in city["developments"])
    assert all(
        len(v["sha256"]) == 64 and v["bytes"] < 12 * 1024 * 1024 for v in manifest["files"].values()
    )


def test_dam_metadata_change_rejects_the_whole_snapshot():
    from shapely.geometry import box

    from scripts.build_sample_dataset import developments, digest, encode

    before = encode({"metas": {"default": {"modified": "old"}}})
    after = encode({"metas": {"default": {"modified": "new"}}})
    entries = [
        {"file": name, "sha256": digest(raw)}
        for name, raw in [("before", before), ("after", after)]
    ]
    inputs = {
        "dam-before": before,
        "dam-after": after,
        "dam-manifest.json": encode({"complete": True, "entries": entries}),
    }
    with pytest.raises(ValueError, match="Inconsistent DAM snapshot"):
        developments(inputs, box(0, 0, 1, 1))


def test_drawn_rails_are_clipped_but_motion_paths_stay_whole():
    from shapely.geometry import box, shape

    from scripts.build_sample_dataset import display_tracks

    geometry = box(0, 0, 1, 1)
    schedule = {"shapes": {"through": {"coordinates": [[-1, 0.5], [2, 0.5]], "distances": [0, 3]}}}
    result = display_tracks(schedule, geometry)
    assert len(result["features"]) == 1
    assert geometry.covers(shape(result["features"][0]["geometry"]))
    assert schedule["shapes"]["through"]["coordinates"] == [[-1, 0.5], [2, 0.5]]
    assert schedule["shapes"]["through"]["distances"] == [0, 3]


def test_real_display_rails_do_not_escape_the_focus_area():
    from shapely.geometry import shape

    city = json.loads((ROOT / "apps/web/src/assets/sample/city.json").read_bytes())
    boundary = shape(city["boundary"]["geometry"])
    assert len(city["display_tracks"]["features"]) > 0
    for feature in city["display_tracks"]["features"]:
        assert boundary.buffer(1e-12).covers(shape(feature["geometry"]))
    assert {f["properties"]["area_id"] for f in city["areas"]["features"]} == {"cbd", "southbank"}


def test_previous_day_is_an_independent_calendar_export_with_shared_display_shapes():
    city = json.loads((ROOT / "apps/web/src/assets/sample/city.json").read_bytes())
    previous = json.loads((ROOT / "apps/web/src/assets/sample/previous-schedule.json").read_bytes())
    assert previous["date"] == "2026-10-07"
    assert len(previous["trips"]) > 4000
    assert {t["service_date"] for t in previous["trips"]} == {"2026-10-06", "2026-10-07"}
    assert set(previous["shapes"]) <= set(city["schedule"]["shapes"])
    assert all(
        city["schedule"]["shapes"][key] == value for key, value in previous["shapes"].items()
    )

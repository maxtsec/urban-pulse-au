"""Exercise the real offline Parquet/dbt boundary, including failed publication."""

import hashlib
import json
import subprocess
from dataclasses import replace
from datetime import timedelta

import duckdb
import polars as pl
import pytest
from google.transit import gtfs_realtime_pb2 as gtfs

from pipelines.local_tram import decode, key, write_inputs
from scripts import local_tram as cli
from tests.test_tram_field_audit import END, START, build_store, fingerprint


def prepared(tmp_path, captures=None):
    out = tmp_path / "analysis"
    write_inputs(
        cli.fixture(START) if captures is None else captures, out, START, END, "synthetic", {}
    )
    return out


def mutate(capture, action):
    msg = gtfs.FeedMessage()
    msg.ParseFromString(capture.body)
    action(msg.entity[0].vehicle)
    return replace(capture, body=msg.SerializeToString())


def rows(directory, table):
    with duckdb.connect(str(directory / "local_tram.duckdb"), read_only=True) as db:
        return db.execute(f"select * from analytics.{table} order by all").fetchall()


def test_real_dbt_build_missing_windows_dedup_and_repeat(tmp_path):
    out = prepared(tmp_path)
    cli.build(out)
    with duckdb.connect(str(out / "local_tram.duckdb"), read_only=True) as db:
        assert db.sql("select count(*) from analytics.mart_area_tram_15m").fetchone() == (192,)
        assert db.sql("select count(*) from analytics.mart_capture_15m").fetchone() == (288,)
        first = db.execute(
            "select observed_vehicle_count, observation_count, median_position_age_seconds, "
            "successful_capture_count, max_success_gap_seconds from "
            "analytics.mart_area_tram_15m where area_id='southbank' order by window_start "
            "limit 1"
        ).fetchone()
        assert first == (1, 1, 30.0, 2, 780.0)
        failed = db.execute(
            "select observed_vehicle_count, failed_capture_count, max_success_gap_seconds "
            "from analytics.mart_area_tram_15m where area_id='southbank' order by "
            "window_start limit 1 offset 1"
        ).fetchone()
        assert failed == (None, 1, 900.0)
        assert db.sql(
            "select observed_vehicle_count from analytics.mart_area_tram_15m where "
            "area_id='melbourne-cbd' order by window_start limit 1"
        ).fetchone() == (0,)
    assert "2026-10-08 00:00:00+00" in (out / "mart_area_tram_15m.csv").read_text()
    before = {p.name: p.read_bytes() for p in out.glob("*.csv")}
    models = rows(out, "int_observations")
    cli.build(out)
    assert before == {p.name: p.read_bytes() for p in out.glob("*.csv")}
    assert models == rows(out, "int_observations")
    assert json.loads((out / "build-success.json").read_text())["result"] == "dbt-build-passed"


@pytest.mark.parametrize("other_vehicle", [False, True])
def test_conflicting_observation_is_isolated_without_hiding_other_windows(tmp_path, other_vehicle):
    captures = cli.fixture(START)
    captures[1] = mutate(captures[1], lambda v: setattr(v.position, "longitude", 144.966))
    if other_vehicle:
        other = mutate(captures[0], lambda v: setattr(v.vehicle, "id", "synthetic-tram-2"))
        captures.append(replace(other, capture_id="other-vehicle", sequence=8))
    out = prepared(tmp_path, captures)
    cli.build(out)
    with duckdb.connect(str(out / "local_tram.duckdb"), read_only=True) as db:
        assert db.sql("select count(*) from analytics.stg_positions").fetchone() == (
            4 + int(other_vehicle),
        )
        assert db.sql("select count(*) from analytics.int_observation_conflicts").fetchone() == (1,)
        assert db.sql(
            "select observed_vehicle_count,conflict_count from analytics.mart_area_tram_15m "
            "where area_id='southbank' order by window_start limit 3"
        ).fetchall() == [(1 if other_vehicle else None, 1), (None, 0), (1, 0)]
    assert (out / "build-success.json").exists()


def test_failed_dbt_build_removes_old_exports(tmp_path):
    captures = cli.fixture(START)
    captures[0] = replace(captures[0], requested_at=captures[0].received_at + timedelta(seconds=1))
    out = prepared(tmp_path, captures)
    (out / "build-success.json").write_text("old")
    (out / "mart_area_tram_15m.csv").write_text("old")
    with pytest.raises(subprocess.CalledProcessError):
        cli.build(out)
    assert not (out / "build-success.json").exists()
    assert not list(out.glob("*.csv"))
    assert not (out / "build.lock").exists()


def test_invalid_times_locations_and_ids_remain_visible(tmp_path):
    captures = cli.fixture(START)
    captures[0] = mutate(captures[0], lambda v: v.ClearField("timestamp"))
    captures[1] = mutate(
        captures[1],
        lambda v: setattr(v, "timestamp", int((START + timedelta(hours=1)).timestamp())),
    )
    captures[5] = mutate(captures[5], lambda v: setattr(v.position, "latitude", float("nan")))
    captures[6] = mutate(captures[6], lambda v: v.vehicle.ClearField("id"))
    out = prepared(tmp_path, captures)
    cli.build(out)
    with duckdb.connect(str(out / "local_tram.duckdb"), read_only=True) as db:
        assert db.sql(
            "select distinct quality_issue from analytics.stg_positions order by 1"
        ).fetchall() == [
            ("future_observed_at",),
            ("invalid_position",),
            ("missing_observed_at",),
            ("missing_vehicle_id",),
        ]
        assert db.sql(
            "select count(*) from analytics.stg_positions where position_age_seconds is not null"
        ).fetchone() == (0,)
        assert db.sql(
            "select sum(unknown_location_count),sum(missing_vehicle_id_count) from "
            "analytics.mart_area_tram_15m where area_id='southbank'"
        ).fetchone() == (1, 1)


def test_valid_empty_feed_is_zero_and_cross_window_repeat_has_older_age(tmp_path):
    original = cli.fixture(START)[0]
    repeated = replace(
        original,
        capture_id="later",
        sequence=2,
        received_at=START + timedelta(minutes=16),
        requested_at=START + timedelta(minutes=16, seconds=-1),
    )
    msg = gtfs.FeedMessage()
    msg.header.gtfs_realtime_version = "2.0"
    empty = replace(
        original,
        capture_id="empty",
        sequence=3,
        body=msg.SerializeToString(),
        received_at=START + timedelta(minutes=31),
        requested_at=START + timedelta(minutes=31, seconds=-1),
    )
    out = prepared(tmp_path, [original, repeated, empty])
    cli.build(out)
    with duckdb.connect(str(out / "local_tram.duckdb"), read_only=True) as db:
        assert db.sql(
            "select observed_vehicle_count,median_position_age_seconds from "
            "analytics.mart_area_tram_15m where area_id='southbank' order by window_start "
            "limit 4"
        ).fetchall() == [(1, 30.0), (1, 930.0), (0, None), (None, None)]


def test_integrity_and_exclusive_build_lock(tmp_path):
    out = prepared(tmp_path)
    (out / "build.lock").write_text("other process")
    with pytest.raises(FileExistsError):
        cli.build(out)
    assert (out / "build.lock").read_text() == "other process"
    (out / "build.lock").unlink()
    with (out / "positions.parquet").open("ab") as f:
        f.write(b"changed")
    with pytest.raises(ValueError, match="parquet_hash_mismatch"):
        cli.build(out)
    assert not (out / "build-success.json").exists()


def test_read_only_v3_skips_pending_and_preserves_store(tmp_path):
    original = cli.fixture(START)[0]
    root = build_store(tmp_path, bodies=[original.body], pending=True)
    # A running collector owns its lock; this reader never opens it.
    (root / "store.lock").write_text("collector owns this")
    before = fingerprint(root)
    captures, evidence = cli.store(root, START, END, 1, None)
    assert len(captures) == 1
    assert captures[0].sequence == 1
    out = tmp_path / "separate-export"
    write_inputs(captures, out, START, END, "synthetic", evidence)
    assert before == fingerprint(root)
    assert pl.read_parquet(out / "positions.parquet").height == 1
    payload = next(root.glob("captures/*/response/payload.bin"))
    payload.write_bytes(b"changed")
    with pytest.raises(ValueError):
        cli.store(root, START, END, 1, None)


def test_probe_checks_saved_bytes_and_paths(tmp_path):
    c = cli.fixture(START)[0]
    path = tmp_path / "01-vehicle-positions.pb"
    path.write_bytes(c.body)
    report = dict(
        schema="transport-source-probe-v1",
        captures=[
            dict(
                feed=c.feed,
                payload=path.name,
                bytes=len(c.body),
                sha256=hashlib.sha256(c.body).hexdigest(),
                requested_at=c.requested_at.isoformat(),
                received_at=c.received_at.isoformat(),
            )
        ],
    )
    (tmp_path / "report.json").write_text(json.dumps(report))
    assert cli.probe(tmp_path)[0][0].body == c.body
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="payload_integrity_failure"):
        cli.probe(tmp_path)
    report["captures"][0]["payload"] = "../outside.pb"
    (tmp_path / "report.json").write_text(json.dumps(report))
    with pytest.raises(ValueError, match="invalid_payload_path"):
        cli.probe(tmp_path)


def test_source_keys_empty_and_half_open_intervals(tmp_path):
    c = cli.fixture(START)[0]
    assert key("vehicle_positions", c, 0) != key("vehicle_positions", c, 1)
    assert key("vehicle_positions", c, 0) == key("vehicle_positions", replace(c, body=b"other"), 0)
    out = tmp_path / "empty"
    write_inputs([replace(c, received_at=END)], out, START, END, "synthetic", {})
    assert pl.read_parquet(out / "positions.parquet").height == 0
    with pytest.raises(ValueError, match="duplicate_capture"):
        prepared(tmp_path, [c, c])
    with pytest.raises(ValueError, match="align"):
        write_inputs([], tmp_path / "bad", START + timedelta(seconds=1), END, "synthetic", {})
    with pytest.raises(ValueError, match="timezone"):
        cli.timestamp("2026-10-08T00:00:00")


def test_decoder_preserves_zero_and_rejects_differential():
    c = mutate(cli.fixture(START)[0], lambda v: setattr(v, "timestamp", 0))
    assert decode(c)[1][0]["observed_at"].year == 1970
    assert decode(replace(c, body=b"invalid"))[0]["quality_issue"] == "invalid_protobuf"
    msg = gtfs.FeedMessage()
    msg.ParseFromString(c.body)
    msg.header.incrementality = gtfs.FeedHeader.DIFFERENTIAL
    assert decode(replace(c, body=msg.SerializeToString()))[0]["payload_valid"] is False

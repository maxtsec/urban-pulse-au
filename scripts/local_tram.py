"""Prepare private analytical Parquet and run an entirely local DuckDB/dbt build."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from google.transit import gtfs_realtime_pb2 as gtfs

from pipelines.local_tram import ROOT, SCHEMAS, Capture, write_inputs
from scripts import tram_field_audit as audit
from urbanpulse.contracts.local_capture import FEEDS, MAX_BYTES, Intent, Manifest


def timestamp(text: str) -> datetime:
    value = datetime.fromisoformat(text)
    if value.tzinfo is None:
        raise ValueError("timezone_required")
    return value.astimezone(UTC)


def probe(directory: Path) -> tuple[list[Capture], dict[str, Any]]:
    body = audit.read_file(directory, "report.json", MAX_BYTES)
    report = json.loads(body)
    if report.get("schema") != "transport-source-probe-v1" or len(report["captures"]) > 11:
        raise ValueError("unsupported_probe")
    store = str(uuid5(NAMESPACE_URL, hashlib.sha256(body).hexdigest()))
    captures = []
    for i, c in enumerate(report["captures"], 1):
        if c["feed"] not in FEEDS:
            raise ValueError("unknown_feed")
        payload = None
        if "payload" in c:
            if c["payload"] != f"{i:02d}-{c['feed']}.pb":
                raise ValueError("invalid_payload_path")
            payload = audit.read_file(directory, c["payload"], MAX_BYTES)
            if len(payload) != c["bytes"] or hashlib.sha256(payload).hexdigest() != c["sha256"]:
                raise ValueError("payload_integrity_failure")
        elif not c.get("error"):
            raise ValueError("missing_payload")
        captures.append(
            Capture(
                store,
                str(uuid5(NAMESPACE_URL, store + ":" + str(i))),
                i,
                c["feed"],
                timestamp(c["requested_at"]),
                timestamp(c["received_at"]) if payload is not None else None,
                "captured" if payload is not None else "fetch-failed",
                payload,
            )
        )
    return captures, dict(report_sha256=hashlib.sha256(body).hexdigest(), source="retained-probe")


def store(
    directory: Path, start: datetime, end: datetime, first: int, last: int | None
) -> tuple[list[Capture], dict[str, Any]]:
    result = audit.audit(directory, start, end, first=first, last=last)
    captures = []
    for sequence, cid, manifest_hash, receipt_hash, payload_hash, _ in result["inventory"]:
        base = f"captures/{cid}"
        intent = Intent.model_validate(audit.document(directory, base + "/intent.json"))
        raw = audit.read_file(directory, base + "/manifest.json")
        if hashlib.sha256(raw).hexdigest() != manifest_hash:
            raise ValueError("manifest_changed_after_audit")
        manifest = Manifest.model_validate_json(raw)
        if str(intent.capture_id) != cid or intent.capture_sequence != sequence:
            raise ValueError("intent_changed_after_audit")
        if manifest.receipt and intent.requested_at != manifest.receipt.requested_at:
            raise ValueError("intent_receipt_mismatch")
        at = manifest.receipt.received_at if manifest.receipt else intent.requested_at
        if not start <= at < end:
            continue
        body = None
        if manifest.receipt:
            raw_receipt = audit.read_file(directory, base + "/response/receipt.json")
            body = audit.read_file(directory, base + "/response/payload.bin", MAX_BYTES)
            if (
                hashlib.sha256(raw_receipt).hexdigest() != receipt_hash
                or hashlib.sha256(body).hexdigest() != payload_hash
            ):
                raise ValueError("input_changed_after_audit")
        captures.append(
            Capture(
                result["store_id"],
                cid,
                sequence,
                intent.product,
                intent.requested_at,
                manifest.receipt.received_at if manifest.receipt else None,
                manifest.outcome,
                body,
            )
        )
    return captures, dict(source="read-only-v3", audit=result)


def fixture(start: datetime) -> list[Capture]:
    """Small explicitly synthetic inputs; silent windows remain visible across the day."""
    rows = []
    store_id = str(uuid5(NAMESPACE_URL, "urbanpulse-local-analytics-fixture"))
    for i, (minute, feed, fail) in enumerate(
        [
            (1, "vehicle-positions", False),
            (2, "vehicle-positions", False),
            (4, "trip-updates", False),
            (5, "service-alerts", False),
            (16, "vehicle-positions", True),
            (32, "vehicle-positions", False),
            (61, "vehicle-positions", False),
        ],
        1,
    ):
        at = start + timedelta(minutes=minute)
        message = gtfs.FeedMessage()
        message.header.gtfs_realtime_version = "2.0"
        if feed == "vehicle-positions":
            v = message.entity.add(id="sample-1").vehicle
            v.vehicle.id = "synthetic-tram-1"
            v.trip.trip_id = "synthetic-trip-1"
            v.trip.route_id = "synthetic-route-1"
            v.trip.start_date = start.strftime("%Y%m%d")
            v.trip.start_time = "08:00:00"
            v.position.latitude = -37.823
            v.position.longitude = 144.965
            v.timestamp = int(
                (
                    start + timedelta(seconds=30) if minute == 2 else at - timedelta(seconds=30)
                ).timestamp()
            )
        rows.append(
            Capture(
                store_id,
                str(uuid5(NAMESPACE_URL, store_id + ":" + str(i))),
                i,
                feed,
                at - timedelta(seconds=1),
                None if fail else at,
                "fetch-failed" if fail else "captured",
                None if fail else message.SerializeToString(),
            )
        )
    return rows


def build(directory: Path) -> None:
    directory = directory.resolve()
    if not (directory / "manifest.json").is_file():
        raise ValueError("analysis_manifest_required")
    lock = directory / "build.lock"
    with lock.open("x", encoding="utf-8") as stream:
        stream.write(str(os.getpid()))
    try:
        # Generated exports are only published after this build and all tests succeed.
        for filename in ("build-success.json", "mart_area_tram_15m.csv", "mart_capture_15m.csv"):
            (directory / filename).unlink(missing_ok=True)
        _build(directory)
    except Exception:
        for filename in ("build-success.json", "mart_area_tram_15m.csv", "mart_capture_15m.csv"):
            (directory / filename).unlink(missing_ok=True)
        raise
    finally:
        lock.unlink()


def _build(directory: Path) -> None:
    directory = directory.resolve()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != "local-tram-analysis-v1" or set(manifest["tables"]) != set(
        SCHEMAS
    ):
        raise ValueError("invalid_analysis_manifest")
    for name in SCHEMAS:
        path = directory / (name + ".parquet")
        if path.is_symlink() or path.stat().st_size > 512 * 1024**2:
            raise ValueError("invalid_parquet_file")
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["tables"][name]["sha256"]:
            raise ValueError("parquet_hash_mismatch")
    env = os.environ.copy()
    env.update(
        URBANPULSE_PARQUET_DIR=directory.as_posix(),
        URBANPULSE_DUCKDB_PATH=(directory / "local_tram.duckdb").as_posix(),
        DBT_SEND_ANONYMOUS_USAGE_STATS="false",
        DBT_USE_COLORS="false",
    )
    project = ROOT / "pipelines" / "dbt_local"
    # Use the active Python environment, independent of PATH or caller working directory.
    command = [
        sys.executable,
        "-c",
        "from dbt.cli.main import cli; cli()",
        "build",
        "--project-dir",
        str(project),
        "--profiles-dir",
        str(project),
        "--target-path",
        str(directory / "target"),
        "--log-path",
        str(directory / "logs"),
    ]
    subprocess.run(command, env=env, check=True, timeout=300)
    import duckdb

    with duckdb.connect(str(directory / "local_tram.duckdb"), read_only=True) as connection:
        connection.execute("SET TimeZone = 'UTC'")
        for table, order in [
            ("mart_area_tram_15m", "window_start,area_id"),
            ("mart_capture_15m", "window_start,feed"),
        ]:
            destination = str(directory / (table + ".csv")).replace("'", "''")
            connection.execute(
                f"COPY (SELECT * FROM analytics.{table} ORDER BY {order}) "
                f"TO '{destination}' (HEADER, DELIMITER ',')"
            )
    (directory / "build-success.json").write_text(
        json.dumps(
            dict(
                input_manifest_sha256=hashlib.sha256(
                    (directory / "manifest.json").read_bytes()
                ).hexdigest(),
                result="dbt-build-passed",
                model_sha256={
                    str(f.relative_to(project)): hashlib.sha256(f.read_bytes()).hexdigest()
                    for f in sorted(project.rglob("*"))
                    if f.is_file() and f.suffix in {".sql", ".yml"}
                },
                cloud_access=False,
            )
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["fixture", "probe", "store", "build"])
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--start", type=timestamp)
    parser.add_argument("--end", type=timestamp)
    parser.add_argument("--first", type=int, default=1)
    parser.add_argument("--last", type=int)
    args = parser.parse_args()
    if args.mode == "build":
        if args.input is None:
            parser.error("build requires --input")
        build(args.input)
        return 0
    if args.output is None or args.start is None or args.end is None:
        parser.error("preparation requires --output, --start and --end")
    output = args.output.resolve()
    if args.mode != "fixture":
        if args.input is None:
            parser.error("probe/store requires --input")
        source = args.input.resolve()
        if output.is_relative_to(source) or source.is_relative_to(output):
            parser.error("output must be separate from input")
    parent = output.parent
    while not parent.exists():
        parent = parent.parent
    if shutil.disk_usage(parent).free < 512 * 1024**2:
        raise ValueError("insufficient_output_reserve")
    evidence: dict[str, Any]
    if args.mode == "fixture":
        captures, evidence = fixture(args.start), dict(source="synthetic")
        kind = "synthetic"
    elif args.mode == "probe":
        captures, evidence = probe(source)
        kind = "recorded-probe"
    else:
        captures, evidence = store(source, args.start, args.end, args.first, args.last)
        modes = {
            mode
            for feed in evidence["audit"]["feeds"].values()
            for mode, count in feed["modes"].items()
            if count
        }
        if len(modes) > 1:
            raise ValueError("mixed_fixture_live_input")
        kind = (
            "empty-store-selection"
            if not modes
            else "recorded-store"
            if modes == {"live"}
            else "synthetic"
        )
    evidence["code_sha256"] = {
        str(f.relative_to(ROOT)): hashlib.sha256(f.read_bytes()).hexdigest()
        for f in [Path(__file__).resolve(), ROOT / "pipelines/local_tram.py", ROOT / "uv.lock"]
    }
    write_inputs(captures, output, args.start, args.end, kind, evidence)
    print(
        json.dumps(
            dict(
                output=str(output),
                dataset_kind=kind,
                captures=len(captures),
                full_normalization=False,
            )
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Local analytical projection, deliberately not the full normalized-history contract."""

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl
from google.protobuf.message import DecodeError  # type: ignore[import-untyped]
from google.transit import gtfs_realtime_pb2 as gtfs
from shapely.geometry import Point, shape  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[1]
STAMP = pl.Datetime("us", "UTC")
SCHEMAS: dict[str, dict[str, Any]] = {
    "captures": {
        "record_key": pl.String,
        "store_id": pl.String,
        "capture_id": pl.String,
        "capture_sequence": pl.Int64,
        "feed": pl.String,
        "requested_at": STAMP,
        "received_at": STAMP,
        "outcome": pl.String,
        "raw_sha256": pl.String,
        "payload_valid": pl.Boolean,
        "quality_issue": pl.String,
    },
    "positions": {
        "record_key": pl.String,
        "capture_id": pl.String,
        "store_id": pl.String,
        "vehicle_id": pl.String,
        "trip_id": pl.String,
        "route_id": pl.String,
        "start_date": pl.String,
        "start_time": pl.String,
        "observed_at": STAMP,
        "received_at": STAMP,
        "latitude": pl.Float64,
        "longitude": pl.Float64,
        "quality_issue": pl.String,
    },
    "memberships": {"record_key": pl.String, "area_id": pl.String, "membership": pl.String},
    "areas": {"area_id": pl.String, "boundary_sha256": pl.String},
    "analysis_run": {"start_at": STAMP, "end_at": STAMP, "dataset_kind": pl.String},
}


@dataclass(frozen=True)
class Capture:
    store_id: str
    capture_id: str
    sequence: int
    feed: str
    requested_at: datetime
    received_at: datetime | None
    outcome: str
    body: bytes | None


def key(table: str, capture: Capture, ordinal: int | None = None) -> str:
    value = ["tram-source-row-v1", table, capture.store_id, capture.capture_id, ordinal, None]
    return hashlib.sha256(
        json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def decode(capture: Capture) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    row: dict[str, Any] = dict(
        record_key=key("captures", capture),
        store_id=capture.store_id,
        capture_id=capture.capture_id,
        capture_sequence=capture.sequence,
        feed=capture.feed,
        requested_at=capture.requested_at,
        received_at=capture.received_at,
        outcome=capture.outcome,
        raw_sha256=hashlib.sha256(capture.body).hexdigest() if capture.body is not None else None,
        payload_valid=False,
        quality_issue=None,
    )
    if capture.body is None:
        return row, []
    feed = gtfs.FeedMessage()
    try:
        feed.ParseFromString(capture.body)
        if not feed.IsInitialized():
            raise DecodeError("missing required fields")
    except DecodeError:
        row["quality_issue"] = "invalid_protobuf"
        return row, []
    if feed.header.incrementality != gtfs.FeedHeader.FULL_DATASET:
        row["quality_issue"] = "unsupported_differential_feed"
        return row, []
    row["payload_valid"] = True
    if capture.feed != "vehicle-positions":
        return row, []
    positions: list[dict[str, Any]] = []
    for ordinal, entity in enumerate(feed.entity):
        if entity.is_deleted or not entity.HasField("vehicle"):
            row["quality_issue"] = "unsupported_position_entity"
            row["payload_valid"] = False
            continue
        v = entity.vehicle

        def field(message: Any, name: str) -> Any:
            return getattr(message, name) if message.HasField(name) else None

        issue = None
        observed = None
        if v.HasField("timestamp"):
            try:
                observed = datetime.fromtimestamp(v.timestamp, UTC)
            except (ValueError, OverflowError, OSError):
                issue = "invalid_observed_at"
        if observed is None:
            issue = issue or "missing_observed_at"
        elif capture.received_at is not None and observed > capture.received_at:
            issue = "future_observed_at"
        lat, lon = field(v.position, "latitude"), field(v.position, "longitude")
        if (
            lat is None
            or lon is None
            or not math.isfinite(lat)
            or not math.isfinite(lon)
            or not (-90 <= lat <= 90 and -180 <= lon <= 180)
        ):
            lat, lon, issue = None, None, "invalid_position"
        vehicle = field(v.vehicle, "id") or None
        if vehicle is None:
            issue = "missing_vehicle_id"
        positions.append(
            dict(
                record_key=key("vehicle_positions", capture, ordinal),
                capture_id=capture.capture_id,
                store_id=capture.store_id,
                vehicle_id=vehicle,
                trip_id=field(v.trip, "trip_id"),
                route_id=field(v.trip, "route_id"),
                start_date=field(v.trip, "start_date"),
                start_time=field(v.trip, "start_time"),
                observed_at=observed,
                received_at=capture.received_at,
                latitude=lat,
                longitude=lon,
                quality_issue=issue,
            )
        )
    return row, positions


def write_inputs(
    captures: list[Capture],
    output: Path,
    start: datetime,
    end: datetime,
    kind: str,
    provenance: dict[str, Any],
) -> None:
    if (
        start.tzinfo is None
        or end.tzinfo is None
        or not 0 < (end - start).total_seconds() <= 26 * 3600
    ):
        raise ValueError("invalid_interval")
    if any(int(t.timestamp()) % 900 or t.microsecond for t in (start, end)):
        raise ValueError("interval_must_align_to_utc_quarter_hours")
    if len(captures) > 10000 or sum(len(c.body or b"") for c in captures) > 2 * 1024**3:
        raise ValueError("capture_limit")
    if len({(c.store_id, c.capture_id) for c in captures}) != len(captures):
        raise ValueError("duplicate_capture")
    rows: dict[str, list[dict[str, Any]]] = {name: [] for name in SCHEMAS}
    boundaries = {}
    for area, filename in [
        ("southbank", "southbank.geojson"),
        ("melbourne-cbd", "melbourne-cbd.geojson"),
    ]:
        body = (ROOT / "tests" / "fixtures" / filename).read_bytes()
        boundaries[area] = shape(json.loads(body)["geometry"])
        rows["areas"].append(dict(area_id=area, boundary_sha256=hashlib.sha256(body).hexdigest()))
    for capture in captures:
        at = capture.received_at or capture.requested_at
        if not start <= at < end:
            continue
        row, positions = decode(capture)
        rows["captures"].append(row)
        rows["positions"].extend(positions)
        if len(rows["positions"]) > 300000:
            raise ValueError("position_row_limit")
        for pos in positions:
            for area, boundary in boundaries.items():
                membership = (
                    "unknown"
                    if pos["latitude"] is None
                    else (
                        "inside"
                        if boundary.covers(Point(pos["longitude"], pos["latitude"]))
                        else "outside"
                    )
                )
                rows["memberships"].append(
                    dict(record_key=pos["record_key"], area_id=area, membership=membership)
                )
    rows["analysis_run"] = [dict(start_at=start, end_at=end, dataset_kind=kind)]
    output.mkdir(parents=True, exist_ok=False)
    manifest: dict[str, Any] = dict(
        format="local-tram-analysis-v1",
        full_normalization=False,
        expiry_authorized=False,
        provenance=provenance,
        tables={},
    )
    for name, schema in SCHEMAS.items():
        path = output / (name + ".parquet")
        pl.DataFrame(rows[name], schema=schema).write_parquet(path)
        manifest["tables"][name] = dict(
            rows=len(rows[name]), sha256=hashlib.sha256(path.read_bytes()).hexdigest()
        )
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

"""Build pinned Southbank tram geometry and synthetic trip observations offline."""

import argparse
import csv
import hashlib
import io
import json
import math
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zipfile import ZipFile

import psycopg

from urbanpulse.config import Settings
from urbanpulse.contracts.events import VehiclePositionChanged

ROOT = Path(__file__).resolve().parents[1]
BOUNDARY = ROOT / "tests/fixtures/southbank.geojson"
OUTPUT = ROOT / "tests/fixtures/map02"
ARCHIVE_SHA256 = "7eb6562c7b19f5685740f3da9f95440bd964681b76c9dc5854f4cb4d08ae393d"
TRAM_SHA256 = "df140ec0fd415d9ce3bd45ff3a47dbb8a65668168fe20a5fd442dc5fa0a62536"
SOURCE_URL = "https://opendata.transport.vic.gov.au/dataset/gtfs-schedule"


def encoded(value):
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()


def read_rows(archive, name):
    if archive.getinfo(name).file_size > 256 * 1024 * 1024:
        raise ValueError("GTFS member exceeds fixture limit")
    with archive.open(name) as source:
        yield from csv.DictReader(io.TextIOWrapper(source, encoding="utf-8-sig"))


def ordered_shapes(rows):
    grouped = defaultdict(dict)
    for row in rows:
        identity = row["shape_id"]
        sequence = int(row["shape_pt_sequence"])
        lon, lat = float(row["shape_pt_lon"]), float(row["shape_pt_lat"])
        if sequence < 0 or sequence in grouped[identity]:
            raise ValueError("Duplicate or invalid shape sequence")
        if not (
            math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90
        ):
            raise ValueError("Invalid shape coordinates")
        grouped[identity][sequence] = [lon, lat]
    shapes = []
    for identity, points in sorted(grouped.items()):
        ordered = [p for _, p in sorted(points.items())]
        if len(ordered) < 2:
            raise ValueError("Shape requires two points")
        shapes.append({"id": identity, "geometry": {"type": "LineString", "coordinates": ordered}})
    return shapes


def select_full_shapes(connection, shapes, boundary):
    """Select by positive-length area overlap; retain every original source vertex."""
    rows = connection.execute(
        """WITH boundary AS (
          SELECT ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),32755) AS geom
        ), shapes AS (
          SELECT value->>'id' AS id, value->'geometry' AS source_geometry,
            ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(value->'geometry'),4326),32755) AS geom
          FROM jsonb_array_elements(%s::jsonb)
        ), selected AS (
          SELECT s.* FROM shapes s CROSS JOIN boundary b
          WHERE s.geom && b.geom
            AND ST_Length(ST_CollectionExtract(ST_Intersection(s.geom,b.geom),2)) > 0.000001
        ), vertices AS (
          SELECT id, (d).path[1] AS ordinal, (d).geom AS point
          FROM selected CROSS JOIN LATERAL ST_DumpPoints(geom) d
        ), edges AS (
          SELECT *, COALESCE(ST_Distance(LAG(point) OVER
            (PARTITION BY id ORDER BY ordinal),point),0) AS length FROM vertices
        ), measured AS (
          SELECT *, SUM(length) OVER (PARTITION BY id ORDER BY ordinal) AS distance_m
          FROM edges
        )
        SELECT s.id, s.source_geometry, array_agg(m.distance_m ORDER BY m.ordinal)
        FROM selected s JOIN measured m ON m.id=s.id
        GROUP BY s.id,s.source_geometry ORDER BY s.id""",
        (json.dumps(boundary), json.dumps(shapes)),
    ).fetchall()
    features = []
    # Source IDs have a portable byte order, independent of database collation.
    for identity, geometry, distances in sorted(rows, key=lambda row: row[0]):
        if len(distances) != len(geometry["coordinates"]) or not all(
            math.isfinite(d) and d >= 0 for d in distances
        ):
            raise ValueError("Invalid full-shape distances")
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "shape_id": identity,
                    "segment_id": f"{identity}/full",
                    "distances_m": distances,
                },
                "geometry": geometry,
            }
        )
    return {"type": "FeatureCollection", "features": features}


def area_vertices(connection, geometry, boundary):
    """Source vertices for authored pilot observations; never trim the shape itself."""
    rows = connection.execute(
        """WITH boundary AS (
          SELECT ST_SetSRID(ST_GeomFromGeoJSON(%s),4326) geom
        ) SELECT f->'properties'->>'shape_id', array_agg((d).path[1]-1 ORDER BY (d).path[1])
        FROM boundary b CROSS JOIN jsonb_array_elements(%s::jsonb->'features') f
        CROSS JOIN LATERAL ST_DumpPoints(ST_SetSRID(ST_GeomFromGeoJSON(f->'geometry'),4326)) d
        WHERE ST_Covers(b.geom,(d).geom) GROUP BY f->'properties'->>'shape_id'""",
        (json.dumps(boundary), json.dumps(geometry)),
    ).fetchall()
    return dict(rows)


def active(trip, calendars, exceptions, day):
    key = (trip["service_id"], day.strftime("%Y%m%d"))
    if key in exceptions:
        return exceptions[key] == "1"
    row = calendars.get(trip["service_id"])
    weekday = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")[
        day.weekday()
    ]
    return (
        row is not None and row["start_date"] <= key[1] <= row["end_date"] and row[weekday] == "1"
    )


def synthetic_fixture(geometry, trips, starts, pilot_vertices):
    started = datetime(2026, 10, 7, tzinfo=UTC)
    frames = []
    links = []
    for index, trip in enumerate(trips):
        feature = next(
            f
            for f in geometry["features"]
            if f["properties"]["shape_id"] == trip["shape_id"]
            and len(f["geometry"]["coordinates"]) >= 6
        )
        points = feature["geometry"]["coordinates"]
        links.append(
            {
                **{
                    k: trip[k]
                    for k in ("trip_id", "route_id", "service_id", "shape_id", "direction_id")
                },
                "service_date": "20261007",
                "start_time": starts[trip["trip_id"]],
                "segment_id": feature["properties"]["segment_id"],
            }
        )
        vertices = pilot_vertices[trip["shape_id"]]
        for sample, vertex in enumerate((vertices[0], vertices[len(vertices) // 2], vertices[-1])):
            revision = index * 3 + sample + 1
            seconds = (revision - 1) * 30
            observed = started + timedelta(seconds=seconds)
            stamp = observed.isoformat().replace("+00:00", "Z")
            vehicle = "yarra-trams/synthetic-map02-tram"
            event = {
                "specversion": "1.0",
                "id": f"map02-synthetic-position-{revision}",
                "source": "urn:urbanpulse:fixture:transport",
                "type": "au.urbanpulse.transport.vehicle-position-changed.v1",
                "subject": vehicle,
                "time": stamp,
                "datacontenttype": "application/json",
                "upmode": "fixture",
                "data": {
                    "schema_version": "1.1",
                    "revision": revision,
                    "provenance": {
                        "provider": "synthetic",
                        "product": "map02-trip-positions",
                        "record_id": vehicle,
                        "capture_ids": [f"map02-synthetic-capture-{revision}"],
                        "source_observed_at": stamp,
                    },
                    "effective_from": stamp,
                    "effective_until": None,
                    "correlation_id": "map02-trip-fixture",
                    "causation_id": None,
                    "state": {
                        "vehicle_id": vehicle,
                        "route_id": trip["route_id"],
                        "position": {"longitude": points[vertex][0], "latitude": points[vertex][1]},
                        "observed_at": stamp,
                        "trip": {
                            "trip_id": trip["trip_id"],
                            "service_date": "20261007",
                            "start_time": starts[trip["trip_id"]],
                            "direction_id": int(trip["direction_id"]),
                        },
                    },
                },
            }
            frames.append(
                {
                    "at_seconds": seconds + 5,
                    "event": VehiclePositionChanged.model_validate(event).model_dump(mode="json"),
                }
            )
    return {
        "schema_version": "map02-trip-fixture-v1",
        "clock_version": "seconds-v1",
        "started_at": started.isoformat().replace("+00:00", "Z"),
        "label": (
            "Synthetic vehicle observations on official static GTFS geometry; authored "
            "times are not timetable predictions"
        ),
        "static_trip_links": links,
        "frames": frames,
    }


def build(path, connection):
    if path.stat().st_size > 300 * 1024 * 1024:
        raise ValueError("Archive too large")
    with path.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != ARCHIVE_SHA256:
            raise ValueError("Archive is not the pinned source release")
    with ZipFile(path) as outer:
        if outer.namelist().count("3/google_transit.zip") != 1:
            raise ValueError("Missing or duplicate tram archive")
        if outer.getinfo("3/google_transit.zip").file_size > 256 * 1024 * 1024:
            raise ValueError("Tram archive too large")
        raw = outer.read("3/google_transit.zip")
    if hashlib.sha256(raw).hexdigest() != TRAM_SHA256:
        raise ValueError("Tram archive hash differs")
    boundary_bytes = BOUNDARY.read_bytes().replace(b"\r\n", b"\n")
    boundary = json.loads(boundary_bytes)["geometry"]
    with ZipFile(io.BytesIO(raw)) as archive:
        if len(archive.namelist()) != len(set(archive.namelist())):
            raise ValueError("Duplicate GTFS member")
        shapes = ordered_shapes(read_rows(archive, "shapes.txt"))
        geometry = select_full_shapes(connection, shapes, boundary)
        pilot_vertices = area_vertices(connection, geometry, boundary)
        trips = list(read_rows(archive, "trips.txt"))
        if len({t["trip_id"] for t in trips}) != len(trips):
            raise ValueError("Ambiguous trip identity")
        route_ids = {r["route_id"] for r in read_rows(archive, "routes.txt")}
        source_shape_ids = {s["id"] for s in shapes}
        if any(
            t["route_id"] not in route_ids or t["shape_id"] not in source_shape_ids for t in trips
        ):
            raise ValueError("Dangling static trip reference")
        routes = defaultdict(set)
        for trip in trips:
            routes[trip["shape_id"]].add(trip["route_id"])
        for f in geometry["features"]:
            f["properties"]["route_ids"] = sorted(routes[f["properties"]["shape_id"]])
        calendars = {r["service_id"]: r for r in read_rows(archive, "calendar.txt")}
        exceptions = (
            {
                (r["service_id"], r["date"]): r["exception_type"]
                for r in read_rows(archive, "calendar_dates.txt")
            }
            if "calendar_dates.txt" in archive.namelist()
            else {}
        )
        frequency = (
            {r["trip_id"] for r in read_rows(archive, "frequencies.txt")}
            if "frequencies.txt" in archive.namelist()
            else set()
        )
        eligible = {
            f["properties"]["shape_id"]
            for f in geometry["features"]
            if len(pilot_vertices.get(f["properties"]["shape_id"], [])) >= 6
        }
        selected = []
        for direction in ("0", "1"):
            candidates = sorted(
                (
                    t
                    for t in trips
                    if t["shape_id"] in eligible
                    and t["direction_id"] == direction
                    and t["trip_id"] not in frequency
                    and active(t, calendars, exceptions, datetime(2026, 10, 7))
                ),
                key=lambda t: t["trip_id"],
            )
            if not candidates:
                raise ValueError("No active fixture trip")
            selected.append(candidates[0])
        wanted = {t["trip_id"] for t in selected}
        first_stops = {}
        for row in read_rows(archive, "stop_times.txt"):
            identity = row["trip_id"]
            if identity in wanted and (
                identity not in first_stops
                or int(row["stop_sequence"]) < int(first_stops[identity]["stop_sequence"])
            ):
                first_stops[identity] = row
        starts = {k: v["departure_time"] for k, v in first_stops.items()}
        observations = synthetic_fixture(geometry, selected, starts, pilot_vertices)
    included = sorted({f["properties"]["shape_id"] for f in geometry["features"]})
    manifest = {
        "schema_version": "southbank-tram-shapes-v1",
        "source_url": SOURCE_URL,
        "source_last_modified": "2026-10-04T01:31:37Z",
        "source_archive_sha256": ARCHIVE_SHA256,
        "tram_archive_member": "3/google_transit.zip",
        "tram_archive_sha256": TRAM_SHA256,
        "boundary_path": "tests/fixtures/southbank.geojson",
        "boundary_sha256": hashlib.sha256(boundary_bytes).hexdigest(),
        "licence": "CC BY 4.0",
        "licence_url": "https://creativecommons.org/licenses/by/4.0/",
        "attribution": (
            "Department of Transport and Planning, Victoria — GTFS Schedule. Selected and "
            "distance-annotated by UrbanPulse; no endorsement implied."
        ),
        "geometry_policy": (
            "Select complete shapes with positive-length Southbank intersection in EPSG:32755, "
            "no buffer; retain all original WGS84 vertices in source order, including "
            "outside-area spans; no clipping, simplification or joining distinct shapes."
        ),
        "distance_policy": (
            "Cumulative projected metres from the complete original shape origin in "
            "source vertex order, starting at zero. Coincident consecutive vertices retain equal "
            "distances. GTFS shape_dist_traveled is "
            "not interpreted as metres."
        ),
        "matching_algorithm": None,
        "matching_tolerance_m": None,
        "matching_status": (
            "Not implemented or approved by this geometry extraction; fixture "
            "observations are synthetic vertices, not live matching evidence."
        ),
        "postgis_version": connection.execute("SELECT postgis_full_version()").fetchone()[0],
        "source_shape_count": len(shapes),
        "included_shape_ids": included,
        "excluded_shape_ids": sorted(source_shape_ids - set(included)),
        "segment_count": len(geometry["features"]),
        "selected_trip_count": len(selected),
        "artifacts": {
            name: {
                "sha256": hashlib.sha256(encoded(value)).hexdigest(),
                "bytes": len(encoded(value)),
            }
            for name, value in [
                ("southbank-tram-shapes.geojson", geometry),
                ("trip-observations.json", observations),
            ]
        },
    }
    return geometry, observations, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    with psycopg.connect(Settings().database_url, connect_timeout=3) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        connection.execute("SET LOCAL statement_timeout = '120s'")
        geometry, observations, manifest = build(args.archive, connection)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, value in [
        ("southbank-tram-shapes.geojson", geometry),
        ("trip-observations.json", observations),
        ("manifest.json", manifest),
    ]:
        (args.output / name).write_bytes(encoded(value))
    print(
        json.dumps(
            {
                "shapes": len(manifest["included_shape_ids"]),
                "segments": manifest["segment_count"],
                "events": len(observations["frames"]),
            }
        )
    )


if __name__ == "__main__":
    main()

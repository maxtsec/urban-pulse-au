"""Verify Southbank/CBD expansion offline, reusing each complete shape once."""

import argparse
import hashlib
import io
import json
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile

import psycopg

from scripts.build_tram_fixture import (
    ARCHIVE_SHA256,
    ROOT,
    TRAM_SHA256,
    encoded,
    ordered_shapes,
    read_rows,
    read_tram_archive,
    select_full_shapes,
)
from urbanpulse.config import Settings

OUTPUT = ROOT / "tests/fixtures/map02-expansion"
BOUNDARIES = {
    "southbank": ROOT / "tests/fixtures/southbank.geojson",
    "melbourne-cbd": ROOT / "tests/fixtures/melbourne-cbd.geojson",
}
PRIMARY = ROOT / "tests/fixtures/map02/southbank-tram-shapes.geojson"
ADDITIONAL_PATH = "tests/fixtures/map02-expansion/cbd-additional-shapes.geojson"


def indexed(collection):
    result = {}
    for feature in collection["features"]:
        identity = feature["properties"]["shape_id"]
        if identity in result:
            raise ValueError("Duplicate shape identity in an area")
        result[identity] = feature
    return result


def additional_shapes(primary, secondary):
    """Shared identity must mean identical geometry, distance and route provenance."""
    first, second = indexed(primary), indexed(secondary)
    for identity in first.keys() & second.keys():
        if first[identity] != second[identity]:
            raise ValueError("Shared shape content differs")
    return {
        "type": "FeatureCollection",
        "features": [second[identity] for identity in sorted(second.keys() - first.keys())],
    }


def build(path, connection):
    with ZipFile(io.BytesIO(read_tram_archive(path))) as archive:
        if len(archive.namelist()) != len(set(archive.namelist())):
            raise ValueError("Duplicate GTFS member")
        shapes = ordered_shapes(read_rows(archive, "shapes.txt"))
        shape_ids = {s["id"] for s in shapes}
        route_ids = {r["route_id"] for r in read_rows(archive, "routes.txt")}
        routes = defaultdict(set)
        for trip in read_rows(archive, "trips.txt"):
            if trip["shape_id"] not in shape_ids or trip["route_id"] not in route_ids:
                raise ValueError("Dangling static trip reference")
            routes[trip["shape_id"]].add(trip["route_id"])
    scopes, areas = {}, {}
    for area, boundary_path in BOUNDARIES.items():
        raw = boundary_path.read_bytes().replace(b"\r\n", b"\n")
        boundary = json.loads(raw)
        geometry = select_full_shapes(connection, shapes, boundary["geometry"])
        for feature in geometry["features"]:
            feature["properties"]["route_ids"] = sorted(routes[feature["properties"]["shape_id"]])
        scopes[area] = geometry
        areas[area] = {
            "name": boundary["properties"]["name"],
            "boundary_path": boundary_path.relative_to(ROOT).as_posix(),
            "boundary_sha256": hashlib.sha256(raw).hexdigest(),
            "shape_ids": sorted(indexed(geometry)),
            "standalone_geometry_bytes": len(encoded(geometry)),
            "vertices": sum(len(f["geometry"]["coordinates"]) for f in geometry["features"]),
        }
    primary_bytes = PRIMARY.read_bytes()
    if primary_bytes != encoded(scopes["southbank"]):
        raise ValueError("Retained Southbank asset differs from this source/build; review refresh")
    additional = additional_shapes(scopes["southbank"], scopes["melbourne-cbd"])
    assets = {}
    for name, content in (
        (PRIMARY.relative_to(ROOT).as_posix(), primary_bytes),
        (ADDITIONAL_PATH, encoded(additional)),
    ):
        assets[name] = {
            "sha256": hashlib.sha256(content).hexdigest(),
            "bytes": len(content),
            "shape_ids": sorted(indexed(json.loads(content))),
        }
    primary_ids = set(areas["southbank"]["shape_ids"])
    secondary_ids = set(areas["melbourne-cbd"]["shape_ids"])
    index = {
        "schema_version": "map02-area-shapes-v1",
        "source_archive_sha256": ARCHIVE_SHA256,
        "tram_archive_sha256": TRAM_SHA256,
        "source_url": "https://opendata.transport.vic.gov.au/dataset/gtfs-schedule",
        "source_last_modified": "2026-10-04T01:31:37Z",
        "licence": "CC BY 4.0",
        "licence_url": "https://creativecommons.org/licenses/by/4.0/",
        "attribution": "DTP Victoria GTFS Schedule; City of Melbourne CLUE boundaries. "
        "Selected and distance-annotated by UrbanPulse; no endorsement implied.",
        "selection_policy": "Positive-length area overlap in EPSG:32755, no buffer; "
        "retain complete original source shapes; point-only contact excluded. "
        "Geometry selection is not vehicle or current-condition membership.",
        "postgis_version": connection.execute("SELECT postgis_full_version()").fetchone()[0],
        "areas": areas,
        "assets": assets,
        "shared_shape_ids": sorted(primary_ids & secondary_ids),
        "unique_shape_count": len(primary_ids | secondary_ids),
        "additional_shape_count": len(secondary_ids - primary_ids),
        "retained_geometry_bytes": sum(a["bytes"] for a in assets.values()),
        "separate_area_geometry_bytes": sum(a["standalone_geometry_bytes"] for a in areas.values()),
        "limits": "Offline geometry verification only; no area API, live source, building, "
        "weather or planning coverage acceptance. Browser loading/rendering not measured.",
    }
    return additional, index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    with psycopg.connect(Settings().database_url, connect_timeout=3) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        connection.execute("SET LOCAL statement_timeout = '120s'")
        additional, index = build(args.archive, connection)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, content in (("cbd-additional-shapes.geojson", additional), ("index.json", index)):
        (args.output / name).write_bytes(encoded(content))
    print(
        json.dumps(
            {
                "areas": {k: len(v["shape_ids"]) for k, v in index["areas"].items()},
                "unique_shapes": index["unique_shape_count"],
                "additional_shapes": index["additional_shape_count"],
                "geometry_bytes": index["retained_geometry_bytes"],
            }
        )
    )


if __name__ == "__main__":
    main()

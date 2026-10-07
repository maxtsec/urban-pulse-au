"""Prepare opt-in browser comparison assets from the pinned complete tram source."""

import argparse
import io
import json
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile

import psycopg

from scripts.build_tram_fixture import (
    ROOT,
    encoded,
    ordered_shapes,
    read_rows,
    read_tram_archive,
    select_full_shapes,
)
from scripts.build_tram_shape_pool import INDEX, build_pool, digest, load_inputs, publish
from urbanpulse.config import Settings


def complete_features(archive_path, connection):
    with ZipFile(io.BytesIO(read_tram_archive(archive_path))) as archive:
        shapes = ordered_shapes(read_rows(archive, "shapes.txt"))
        routes = defaultdict(set)
        for trip in read_rows(archive, "trips.txt"):
            routes[trip["shape_id"]].add(trip["route_id"])
    collection = select_full_shapes(connection, shapes, None)
    result = {}
    for feature in collection["features"]:
        identity = feature["properties"]["shape_id"]
        feature["properties"]["route_ids"] = sorted(routes[identity])
        result[identity] = feature
    return result


def route_pool(index, features):
    """Experimental route units include ALL source shapes for each required route."""
    by_route = defaultdict(dict)
    for identity, feature in sorted(features.items()):
        if feature["properties"]["shape_id"] != identity:
            raise ValueError("Mismatched shape identity")
        for route in feature["properties"]["route_ids"]:
            by_route[route][identity] = feature
    # Reuse the baseline manifest's provenance, not its object layout.
    baseline, baseline_report = build_pool(index, features)
    files, areas = {}, {}
    for area_id, area in sorted(index["areas"].items()):
        needed = sorted(area["shape_ids"])
        routes = sorted({r for s in needed for r in features[s]["properties"]["route_ids"]})
        fetched, references = set(), {}
        for route in routes:
            raw = encoded(
                {
                    "schema_version": "experimental-tram-route-v1",
                    "route_id": route,
                    "features": list(by_route[route].values()),
                }
            )
            checksum = digest(raw)
            path = f"objects/{checksum}.json"
            files[path] = raw
            references[route] = {"path": path, "sha256": checksum, "bytes": len(raw)}
            fetched.update(by_route[route])
        if not set(needed) <= fetched:
            raise ValueError("Required shape has no route")
        original = baseline_report["areas"][area_id]["manifest"]
        manifest = json.loads(baseline[original["path"]])
        manifest.pop("shapes")
        manifest.update(
            schema_version="experimental-tram-route-area-v1",
            chunk_policy="experimental-full-route-v1",
            shape_ids=needed,
            objects=references,
        )
        raw = encoded(manifest)
        checksum = digest(raw)
        path = f"areas/{checksum}.json"
        files[path] = raw
        areas[area_id] = {
            "manifest": {"path": path, "sha256": checksum, "bytes": len(raw)},
            "shape_count": len(needed),
            "extra_shapes": len(fetched - set(needed)),
            "cold_requests": 1 + len(references),
            "cold_bytes": len(raw) + sum(r["bytes"] for r in references.values()),
        }
    return files, {"areas": areas}


def comparison(index, full_features, retained_features):
    for identity, feature in retained_features.items():
        if encoded(full_features.get(identity)) != encoded(feature):
            raise ValueError("Full source differs from retained area geometry")
    files, layouts = {}, {}
    for name, builder in (("shape", build_pool), ("route", route_pool)):
        assets, report = builder(index, full_features)
        files.update({f"{name}/{path}": raw for path, raw in assets.items()})
        layouts[name] = report["areas"]
    report = {
        "schema_version": "tram-chunk-comparison-v1",
        "source_revision": index["tram_archive_sha256"],
        "complete_source_shapes": len(full_features),
        "layouts": layouts,
        "required_shapes": {a: sorted(v["shape_ids"]) for a, v in index["areas"].items()},
    }
    files["comparison.json"] = encoded(report)
    return files, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    retained = load_inputs(index, ROOT)
    with psycopg.connect(Settings().database_url) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        connection.execute("SET LOCAL statement_timeout = '120s'")
        full = complete_features(args.archive, connection)
    files, report = comparison(index, full, retained)
    for name in sorted(files, key=lambda n: (n == "comparison.json", n)):
        publish(args.output / name, files[name])
    print(json.dumps(report))


if __name__ == "__main__":
    main()

"""Build the reviewed static building layer from a retained Southbank source export."""

import argparse
import hashlib
import json
import math
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATASET = (
    "https://data.melbourne.vic.gov.au/api/explore/v2.1/catalog/datasets/2023-building-footprints"
)
BOUNDARY = ROOT / "tests/fixtures/southbank.geojson"
FIXTURE = ROOT / "apps/web/src/assets/southbank-buildings.geojson"
MANIFEST = ROOT / "tests/fixtures/southbank-buildings.manifest.json"


def export_query(boundary: dict[str, Any]) -> str:
    def polygon(rings: list[Any]) -> str:
        return (
            "("
            + ",".join("(" + ",".join(f"{p[0]} {p[1]}" for p in ring) + ")" for ring in rings)
            + ")"
        )

    geometry = boundary["geometry"]
    if geometry["type"] == "MultiPolygon":
        wkt = "MULTIPOLYGON(" + ",".join(polygon(p) for p in geometry["coordinates"]) + ")"
    else:
        wkt = "POLYGON" + polygon(geometry["coordinates"])
    return f"intersects(geo_shape, geom'{wkt}')"


def polygon_coordinates(rings: Any) -> list[Any]:
    if not isinstance(rings, list) or not rings:
        raise ValueError("Missing polygon rings")
    result = []
    for ring in rings:
        if not isinstance(ring, list) or len(ring) < 4:
            raise ValueError("Invalid ring")
        points = []
        for point in ring:
            if not isinstance(point, list) or len(point) != 2:
                raise ValueError("Expected two coordinates")
            if any(
                isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                for v in point
            ):
                raise ValueError("Non-finite coordinates")
            if not (-180 <= point[0] <= 180 and -90 <= point[1] <= 90):
                raise ValueError("Coordinates out of bounds")
            points.append([round(v, 6) for v in point])
        if points[0] != points[-1] or len({tuple(p) for p in points[:-1]}) < 3:
            raise ValueError("Unclosed or collapsed ring")
        result.append(points)
    return result


def transform(source: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if source.get("type") != "FeatureCollection":
        raise ValueError("Expected a GeoJSON feature collection")
    included = []
    excluded: Counter[str] = Counter()
    rejected = 0
    for feature in source["features"]:
        props = feature["properties"]
        if props.get("footprint_type") != "Structure":
            excluded[str(props.get("footprint_type"))] += 1
            continue
        try:
            values = [
                props[k]
                for k in (
                    "footprint_min_elevation",
                    "footprint_max_elevation",
                    "structure_min_elevation",
                )
            ]
            if any(
                isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                for v in values
            ):
                raise ValueError("Missing or non-finite height")
            minimum, maximum, ground = values
            base, top = round(minimum - ground, 6), round(maximum - ground, 6)
            if base < 0 or top <= base:
                raise ValueError("Invalid relative height")
            geometry = feature["geometry"]
            if geometry["type"] == "Polygon":
                coordinates = polygon_coordinates(geometry["coordinates"])
            elif geometry["type"] == "MultiPolygon" and geometry["coordinates"]:
                coordinates = [polygon_coordinates(p) for p in geometry["coordinates"]]
            else:
                raise ValueError("Unsupported geometry")
            captured = datetime.strptime(props["date_captured"], "%Y%m%d").date().isoformat()
            structure_id = str(props["structure_id"])
            if not structure_id or props["structure_id"] is None:
                raise ValueError("Missing structure identity")
        except (KeyError, TypeError, ValueError):
            rejected += 1
            continue
        included.append(
            {
                "type": "Feature",
                "geometry": {"type": geometry["type"], "coordinates": coordinates},
                "properties": {
                    "structure_id": structure_id,
                    "footprint_type": "Structure",
                    "base_m": base,
                    "top_m": top,
                    "date_captured": captured,
                },
            }
        )
    included.sort(key=lambda f: json.dumps(f, sort_keys=True))
    return {"type": "FeatureCollection", "features": included}, {
        "source_count": len(source["features"]),
        "included_count": len(included),
        "excluded_by_type": dict(sorted(excluded.items())),
        "rejected_structure_count": rejected,
        "structure_count": len({f["properties"]["structure_id"] for f in included}),
        "capture_dates": dict(
            sorted(Counter(f["properties"]["date_captured"] for f in included).items())
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Retained unfiltered GeoJSON export using the manifest's boundary-intersection query",
    )
    parser.add_argument("--retrieved-on", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    raw = args.source.read_bytes()
    fixture, counts = transform(json.loads(raw))
    encoded = (
        json.dumps(fixture, separators=(",", ":"), sort_keys=True, allow_nan=False) + "\n"
    ).encode()
    FIXTURE.write_bytes(encoded)
    manifest = {
        "dataset_id": "2023-building-footprints",
        "source_url": "https://data.melbourne.vic.gov.au/explore/dataset/2023-building-footprints/",
        "export_url": DATASET + "/exports/geojson",
        "export_query": {"where": export_query(json.loads(BOUNDARY.read_text(encoding="utf-8")))},
        "retrieved_on": args.retrieved_on.isoformat(),
        "licence": "CC BY 4.0",
        "licence_url": "https://creativecommons.org/licenses/by/4.0/",
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "boundary_path": "tests/fixtures/southbank.geojson",
        "boundary_sha256": hashlib.sha256(BOUNDARY.read_bytes()).hexdigest(),
        "fixture_path": FIXTURE.relative_to(ROOT).as_posix(),
        "fixture_sha256": hashlib.sha256(encoded).hexdigest(),
        "fixture_bytes": len(encoded),
        "counts": counts,
        "modifications": (
            "Whole intersecting Structure polygons retained; non-Structure types excluded; "
            "invalid coordinates/elevations rejected without defaults; "
            "coordinates rounded to 6 decimal places; "
            "base/top relative to structure_min_elevation; "
            "only structure identity/type, relative heights and capture date retained. "
            "Visual context only; no live polling."
        ),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(counts))


if __name__ == "__main__":
    main()

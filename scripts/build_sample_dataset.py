"""Build the public mixed-source sample offline from a hash-pinned source pack."""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import io
import json
import math
import zipfile
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

from shapely.geometry import Point, box, mapping, shape
from shapely.ops import unary_union

from scripts.build_building_fixture import transform

ROOT = Path(__file__).resolve().parents[1]
DAY = date(2026, 10, 8)
DAY_MS = 86_400_000
BBOX = (144.945, -37.836, 144.979, -37.804)
CREDIT = [
    {
        "name": "City of Melbourne â€” building footprints",
        "url": "https://data.melbourne.vic.gov.au/explore/dataset/2023-building-footprints/",
        "changes": (
            "Structure polygons only; relative heights; coordinates rounded to six "
            "decimals; duplicates removed."
        ),
    },
    {
        "name": "Department of Transport and Planning â€” GTFS Schedule",
        "url": "https://opendata.transport.vic.gov.au/dataset/gtfs-schedule",
        "changes": (
            "Tram member only; service-calendar selection; full intersecting shapes; "
            "scheduled dwell and constant speed between stops; drawn rails clipped to area "
            "while motion paths remain whole. Positions are simulated, "
            "not observed."
        ),
    },
    {
        "name": "City of Melbourne â€” Development Activity Monitor",
        "url": "https://data.melbourne.vic.gov.au/explore/dataset/development-activity-monitor/",
        "changes": (
            "CBD and Southbank records; original status and source date retained. Models "
            "indicate DAM projects, not actual worksite locations or obstructions."
        ),
    },
    {
        "name": "City of Melbourne â€” CLUE small areas",
        "url": "https://data.melbourne.vic.gov.au/explore/dataset/small-areas-for-census-of-land-use-and-employment-clue/",
        "changes": "CBD and Southbank geometries combined for display; no analysis buffer.",
    },
    {
        "name": (
            "State of Victoria, Department of Transport and Planning â€” Vicmap Transport Road Line"
        ),
        "url": "https://discover.data.vic.gov.au/dataset/vicmap-transport-road-line",
        "changes": (
            "Street centre lines only, clipped to local display bounds; names retained; "
            "coordinates rounded to six decimals. Not road widths or routing."
        ),
    },
    {
        "name": (
            "State of Victoria, Department of Transport and Planning â€” Vicmap Hydro Water Polygon"
        ),
        "url": "https://discover.data.vic.gov.au/dataset/vicmap-hydro-water-polygon",
        "changes": (
            "Watercourse polygons intersecting local bounds, clipped for visual context; "
            "not a flood boundary."
        ),
    },
]


def encode(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_pack(path: Path, lock_path: Path) -> dict[str, bytes]:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    raw = path.read_bytes()
    if digest(raw) != lock["archive_sha256"]:
        raise ValueError("Source archive hash mismatch")
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        if len(z.namelist()) != len(set(z.namelist())) or set(z.namelist()) != set(lock["members"]):
            raise ValueError("Unexpected source inventory")
        result = {name: z.read(name) for name in sorted(z.namelist())}
    if any(digest(raw) != lock["members"][name] for name, raw in result.items()):
        raise ValueError("Source member hash mismatch")
    return result


def rows(z: zipfile.ZipFile, name: str):
    with z.open(name) as stream:
        yield from csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig"))


def service_ids(
    calendar: list[dict[str, str]], exceptions: list[dict[str, str]], day: date
) -> set[str]:
    value = day.strftime("%Y%m%d")
    weekday = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][
        day.weekday()
    ]
    active = {
        r["service_id"]
        for r in calendar
        if r["start_date"] <= value <= r["end_date"] and r[weekday] == "1"
    }
    for r in exceptions:
        if r["date"] == value:
            if r["exception_type"] == "1":
                active.add(r["service_id"])
            elif r["exception_type"] == "2":
                active.discard(r["service_id"])
    return active


def time_ms(value: str) -> int:
    h, m, s = map(int, value.split(":"))
    if h < 0 or not 0 <= m < 60 or not 0 <= s < 60:
        raise ValueError("Invalid schedule clock")
    return ((h * 60 + m) * 60 + s) * 1000


def metres(a: list[float], b: list[float]) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, [*a, *b])
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 12_742_000 * math.asin(min(1, math.sqrt(h)))


def along(value: float, source_distances: list[float], distances: list[float]) -> float:
    if not math.isfinite(value) or value < source_distances[0] or value > source_distances[-1]:
        raise ValueError("Stop distance outside shape")
    i = bisect.bisect_right(source_distances, value)
    if i == len(source_distances):
        return distances[-1]
    a, b = source_distances[i - 1 : i + 1]
    return round(distances[i - 1] + (value - a) / (b - a) * (distances[i] - distances[i - 1]), 3)


def timetable(raw: bytes, boundary, target_day: date = DAY) -> tuple[dict, dict]:
    rejected: Counter[str] = Counter()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        grouped = defaultdict(list)
        for r in rows(z, "shapes.txt"):
            grouped[r["shape_id"]].append(r)
        selected, original = {}, {}
        for key, points in sorted(grouped.items()):
            points.sort(key=lambda r: int(r["shape_pt_sequence"]))
            coordinates = [[float(r["shape_pt_lon"]), float(r["shape_pt_lat"])] for r in points]
            if len(coordinates) < 2 or not shape(
                {"type": "LineString", "coordinates": coordinates}
            ).intersects(boundary):
                continue
            source_d = [float(r["shape_dist_traveled"]) for r in points]
            if any(b <= a for a, b in zip(source_d, source_d[1:], strict=False)):
                rejected["non_increasing_shape_distance"] += 1
                continue
            distances = [0.0]
            for a, b in zip(coordinates, coordinates[1:], strict=False):
                distances.append(round(distances[-1] + metres(a, b), 3))
            selected[key] = {"coordinates": coordinates, "distances": distances}
            original[key] = source_d
        calendar, exceptions = list(rows(z, "calendar.txt")), list(rows(z, "calendar_dates.txt"))
        days = [(target_day - timedelta(days=1), -DAY_MS), (target_day, 0)]
        active = {day: service_ids(calendar, exceptions, day) for day, _ in days}
        routes = {r["route_id"]: r for r in rows(z, "routes.txt")}
        trips = {
            r["trip_id"]: r
            for r in rows(z, "trips.txt")
            if r["shape_id"] in selected and any(r["service_id"] in ids for ids in active.values())
        }
        stops = defaultdict(list)
        for r in rows(z, "stop_times.txt"):
            if r["trip_id"] in trips:
                stops[r["trip_id"]].append(r)
        output = []
        for key, trip in sorted(trips.items()):
            try:
                ordered = sorted(stops[key], key=lambda r: int(r["stop_sequence"]))
                knots = [
                    [
                        time_ms(r["arrival_time"]),
                        time_ms(r["departure_time"]),
                        along(
                            float(r["shape_dist_traveled"]),
                            original[trip["shape_id"]],
                            selected[trip["shape_id"]]["distances"],
                        ),
                    ]
                    for r in ordered
                ]
                if (
                    len(knots) < 2
                    or any(a > d for a, d, _ in knots)
                    or any(
                        b[0] < a[1] or b[2] < a[2] for a, b in zip(knots, knots[1:], strict=False)
                    )
                ):
                    raise ValueError("Invalid stop progression")
            except (KeyError, ValueError):
                rejected["unusable_trip"] += 1
                continue
            for day, offset in days:
                if (
                    trip["service_id"] not in active[day]
                    or knots[-1][1] + offset <= 0
                    or knots[0][0] + offset >= DAY_MS
                ):
                    continue
                output.append(
                    {
                        "id": f"schedule:{day.isoformat()}:{key}",
                        "trip_id": key,
                        "service_date": day.isoformat(),
                        "route_id": trip["route_id"],
                        "route": routes[trip["route_id"]]["route_short_name"],
                        "headsign": trip["trip_headsign"],
                        "shape": trip["shape_id"],
                        "stops": [[a + offset, d + offset, s] for a, d, s in knots],
                    }
                )
        used = {t["shape"] for t in output}
        return {
            "date": target_day.isoformat(),
            "timezone": "Australia/Melbourne",
            "trips": output,
            "shapes": {k: v for k, v in selected.items() if k in used},
        }, dict(rejected)


def round_geometry(geometry: dict) -> dict:
    def rounded(value):
        if isinstance(value, (list, tuple)):
            return [rounded(v) for v in value]
        return round(value, 6)

    return {"type": geometry["type"], "coordinates": rounded(geometry["coordinates"])}


def basemap(inputs: dict[str, bytes], name: str) -> dict:
    features = []
    ids = json.loads(inputs[name + "-ids.json"])["objectIds"]
    seen = set()
    for filename in sorted(inputs):
        if filename.startswith(name + "-") and filename.endswith(".geojson"):
            data = json.loads(inputs[filename])
            if data.get("exceededTransferLimit"):
                raise ValueError("Truncated Vicmap page")
            for f in data["features"]:
                key = f["properties"]["id"]
                if key in seen:
                    raise ValueError("Duplicate source feature")
                seen.add(key)
                p = f["properties"]
                if name == "roads" and p["feature_type_code"] not in (
                    "road",
                    "bridge",
                    "tunnel",
                    "roundabout",
                ):
                    continue
                if name == "water" and not p["feature_type_code"].startswith("watercourse_area"):
                    continue
                g = shape(f["geometry"])
                if not g.is_valid:
                    raise ValueError("Invalid Vicmap geometry")
                clipped = g.intersection(box(*BBOX))
                if clipped.is_empty:
                    continue
                features.append(
                    {
                        "type": "Feature",
                        "geometry": round_geometry(mapping(clipped)),
                        "properties": {
                            "id": key,
                            "name": p.get("ezi_road_name_label")
                            if name == "roads"
                            else p.get("name"),
                        },
                    }
                )
    if seen != set(ids):
        raise ValueError("Incomplete Vicmap inventory")
    return {
        "type": "FeatureCollection",
        "features": sorted(features, key=lambda f: f["properties"]["id"]),
    }


def developments(inputs: dict[str, bytes], boundary) -> tuple[list, str]:
    manifest = json.loads(inputs["dam-manifest.json"])
    entries = manifest["entries"]
    for e in entries:
        if digest(inputs["dam-" + e["file"]]) != e["sha256"]:
            raise ValueError("DAM hash mismatch")
    before = json.loads(inputs["dam-" + entries[0]["file"]])["metas"]["default"]
    after = json.loads(inputs["dam-" + entries[-1]["file"]])["metas"]["default"]
    if before != after or not manifest["complete"]:
        raise ValueError("Inconsistent DAM snapshot")
    grouped = defaultdict(list)
    for e in entries[1:-1]:
        grouped[e["params"]["where"]].append(e)
    records = []
    for pages in grouped.values():
        pages.sort(key=lambda e: int(e["params"]["offset"]))
        count = 0
        for e in pages:
            page = json.loads(inputs["dam-" + e["file"]])
            if int(e["params"]["offset"]) != count:
                raise ValueError("DAM page gap")
            records.extend(page["results"])
            count += len(page["results"])
            if page["total_count"] != json.loads(inputs["dam-" + pages[0]["file"]])["total_count"]:
                raise ValueError("DAM total changed")
        if count != page["total_count"]:
            raise ValueError("Incomplete DAM area")
    if len({r["development_key"] for r in records}) != len(records):
        raise ValueError("Duplicate DAM record")
    result = []
    for r in sorted(records, key=lambda r: r["development_key"]):
        p = r["geopoint"]
        position = {"longitude": p["lon"], "latitude": p["lat"]} if p else None
        result.append(
            {
                "development_key": r["development_key"],
                "name": "Development " + r["development_key"],
                "status": r["status"],
                "clue_small_area": r["clue_small_area"],
                "position": position,
                "year_completed": r["year_completed"],
                "applicable": bool(p and boundary.covers(Point(p["lon"], p["lat"]))),
            }
        )
    return result, before["modified"]


def display_tracks(schedule: dict, boundary) -> dict:
    """Clip only drawn rails. Simulation keeps its full shape and distance index."""
    features = []
    for shape_id, item in sorted(schedule["shapes"].items()):
        geometry = shape({"type": "LineString", "coordinates": item["coordinates"]})
        clipped = geometry.intersection(boundary)
        parts = (
            [clipped] if clipped.geom_type == "LineString" else list(getattr(clipped, "geoms", ()))
        )
        for part in parts:
            if part.geom_type != "LineString" or part.is_empty or part.length == 0:
                continue
            features.append(
                {"type": "Feature", "properties": {"shape_id": shape_id}, "geometry": mapping(part)}
            )
    return {"type": "FeatureCollection", "features": features}


def build(pack: Path, lock: Path, output: Path) -> dict:
    inputs = source_pack(pack, lock)
    boundaries = [json.loads(inputs[n]) for n in ("southbank.geojson", "cbd.geojson")]
    boundary = unary_union([shape(b["geometry"]) for b in boundaries])
    schedule, rejected = timetable(inputs["tram.zip"], boundary)
    previous_schedule, previous_rejected = timetable(
        inputs["tram.zip"], boundary, DAY - timedelta(days=1)
    )
    sites, dam_date = developments(inputs, boundary)
    buildings = []
    counts = {}
    for area in ("southbank", "cbd"):
        data, counts[area] = transform(json.loads(inputs[area + "-buildings.geojson"]))
        buildings.extend(data["features"])
    buildings = list({digest(encode(f)): f for f in buildings}.values())
    buildings.sort(key=encode)
    data = {
        "boundary": {
            "type": "Feature",
            "geometry": mapping(boundary),
            "properties": boundaries[0]["properties"],
        },
        "schedule": schedule,
        "display_tracks": display_tracks(schedule, boundary),
        "areas": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": b["geometry"],
                    "properties": {"area_id": area_id, "name": name},
                }
                for b, area_id, name in zip(
                    boundaries, ["southbank", "cbd"], ["Southbank", "CBD"], strict=True
                )
            ],
        },
        "focus_mask": {
            "type": "Feature",
            "geometry": mapping(box(*BBOX).difference(boundary)),
            "properties": {},
        },
        "developments": sites,
        "dam_date": dam_date,
        "roads": basemap(inputs, "roads"),
        "water": basemap(inputs, "water"),
    }
    output.mkdir(parents=True, exist_ok=True)
    files = {}
    for name, value in [
        ("city.json", data),
        ("previous-schedule.json", previous_schedule),
        ("buildings.geojson", {"type": "FeatureCollection", "features": buildings}),
    ]:
        raw = encode(value)
        if len(raw) > 12 * 1024 * 1024:
            raise ValueError("Sample file size limit exceeded")
        (output / name).write_bytes(raw)
        files[name] = {"bytes": len(raw), "sha256": digest(raw)}
    manifest = {
        "version": "schedule-sample-v1",
        "date": DAY.isoformat(),
        "licence": "CC BY 4.0",
        "licence_url": "https://creativecommons.org/licenses/by/4.0/",
        "source_archive_sha256": digest(pack.read_bytes()),
        "files": files,
        "attribution": CREDIT,
        "building_counts": counts,
        "trip_count": len(schedule["trips"]),
        "previous_day": {
            "date": previous_schedule["date"],
            "trip_count": len(previous_schedule["trips"]),
            "schedule_exclusions": previous_rejected,
        },
        "shape_count": len(schedule["shapes"]),
        "dam_count": len(sites),
        "schedule_exclusions": rejected,
        "dam_date": dam_date,
        "truth": {
            "trams": "Schedule simulation, not live",
            "weather": "Synthetic",
            "developments": "DAM status, not actual worksite location",
            "buildings": "Historical surveyed footprints",
        },
        "source_provenance": {
            "gtfs": json.loads(inputs["gtfs-provenance.json"]),
            "vicmap_and_cbd": json.loads(inputs["receipts.json"]),
            "southbank_buildings": json.loads(inputs["southbank-buildings-provenance.json"]),
            "dam": json.loads(inputs["dam-manifest.json"]),
        },
    }
    (output / "manifest.json").write_bytes(encode(manifest))
    return manifest


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=ROOT / "apps/web/src/assets/sample")
    args = p.parse_args()
    m = build(ROOT / "sample-data/sources.zip", ROOT / "sample-data/sources.lock.json", args.output)
    print(
        json.dumps(
            {
                k: m[k]
                for k in ["files", "trip_count", "shape_count", "dam_count", "schedule_exclusions"]
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

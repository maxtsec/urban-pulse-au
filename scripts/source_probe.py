"""Bounded public reading probes, with retained responses and offline replay."""

import argparse
import hashlib
import json
import math
import subprocess
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import httpx

ROOT = Path(__file__).resolve().parents[1]
DAM = "https://data.melbourne.vic.gov.au/api/explore/v2.1/catalog/datasets/development-activity-monitor"
WEATHER = "https://api.open-meteo.com/v1/forecast"
AREAS = {"Southbank": (-37.825, 144.963), "Melbourne (CBD)": (-37.814, 144.963)}
VARIABLES = (
    "temperature_2m",
    "precipitation",
    "rain",
    "weather_code",
    "cloud_cover",
    "wind_speed_10m",
    "is_day",
)
MAX_REQUESTS = 16
MAX_BYTES = 2 * 1024 * 1024
MAX_SECONDS = 180


def record(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(k, str) for k in value):
        raise ValueError("Expected an object")
    return cast(dict[str, Any], value)


def decode(raw: bytes) -> dict[str, Any]:
    def invalid(value: str) -> None:
        raise ValueError("Non-finite JSON value: " + value)

    return record(json.loads(raw, parse_constant=invalid))


def weather_summary(data: dict[str, Any]) -> dict[str, Any]:
    current, units = record(data.get("current")), record(data.get("current_units"))
    if (
        type(current.get("time")) is not int
        or units.get("time") != "unixtime"
        or data.get("utc_offset_seconds") != 0
    ):
        raise ValueError("Expected explicit UTC epoch reading time")
    expected = {
        "temperature_2m": "°C",
        "precipitation": "mm",
        "rain": "mm",
        "cloud_cover": "%",
        "wind_speed_10m": "m/s",
        "weather_code": "wmo code",
        "is_day": "",
    }
    if any(units.get(k) != v for k, v in expected.items()):
        raise ValueError("Unexpected weather units")
    missing = []
    for field in VARIABLES:
        value = current.get(field)
        if value is None:
            missing.append(field)
        elif (not isinstance(value, (int, float)) or isinstance(value, bool)) or not math.isfinite(
            value
        ):
            raise ValueError("Invalid weather value")
    return {
        "effective_at": datetime.fromtimestamp(current["time"], UTC).isoformat(),
        "interval_seconds": current.get("interval"),
        "values": {k: current.get(k) for k in VARIABLES},
        "units": units,
        "missing": missing,
        "returned_grid": {k: data.get(k) for k in ("latitude", "longitude", "elevation")},
        "requested_model": "best_match",
        "resolved_model": None,
        "warning_coverage": "not_evaluated",
    }


def planning_summary(pages: list[dict[str, Any]], area: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    totals = set()
    for page in pages:
        total = page.get("total_count")
        if type(total) is not int or total < 0 or not isinstance(page.get("results"), list):
            raise ValueError("Invalid DAM page")
        totals.add(total)
        rows.extend(record(row) for row in page["results"])
    if any(row.get("clue_small_area") != area for row in rows):
        raise ValueError("DAM returned an unrequested area")
    keys = [row.get("development_key") for row in rows]
    if any(not isinstance(k, str) or not k for k in keys):
        raise ValueError("Missing development identity")
    missing_positions = 0
    for row in rows:
        if not isinstance(row.get("status"), str):
            raise ValueError("Missing original status")
        point = row.get("geopoint")
        if point is None:
            missing_positions += 1
            continue
        point = record(point)
        for axis, bound in (("lat", 90), ("lon", 180)):
            value = point.get(axis)
            if (
                (not isinstance(value, (int, float)) or isinstance(value, bool))
                or not math.isfinite(value)
                or abs(value) > bound
            ):
                raise ValueError("Invalid DAM point")
    unique = len(set(keys))
    return {
        "records": len(rows),
        "advertised_totals": sorted(totals),
        "unique_keys": unique,
        "missing_positions": missing_positions,
        "statuses": dict(sorted(Counter(str(row.get("status")) for row in rows).items())),
        "pages_complete": len(totals) == 1 and len(rows) == unique == next(iter(totals)),
        "geography_basis": "provider CLUE label; spatial membership not revalidated",
        "per_record_updated_at": None,
    }


class Capture:
    def __init__(self, folder: Path, client: httpx.Client) -> None:
        folder.mkdir(parents=True, exist_ok=False)
        self.folder, self.client = folder, client
        self.started = time.monotonic()
        self.entries: list[dict[str, Any]] = []
        self.manifest: dict[str, Any] = {
            "schema": "bounded-source-probe-v1",
            "source_sha": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "dirty": bool(
                subprocess.check_output(
                    ["git", "status", "--porcelain"], cwd=ROOT, text=True
                ).strip()
            ),
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "started_at": datetime.now(UTC).isoformat(),
            "complete": False,
            "entries": self.entries,
        }
        self.save()

    def save(self) -> None:
        (self.folder / "manifest.json").write_text(
            json.dumps(self.manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def get(self, name: str, url: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        if len(self.entries) >= MAX_REQUESTS or time.monotonic() - self.started >= MAX_SECONDS:
            raise ValueError("Probe request/time budget exhausted")
        entry: dict[str, Any] = {
            "name": name,
            "url": url,
            "params": params or {},
            "requested_at": datetime.now(UTC).isoformat(),
            "file": f"{len(self.entries):02d}.json",
        }
        self.entries.append(entry)
        self.save()
        payload = bytearray()
        with self.client.stream("GET", url, params=params) as response:
            entry["http_status"] = response.status_code
            self.save()
            response.raise_for_status()
            for chunk in response.iter_bytes():
                payload.extend(chunk)
                if len(payload) > MAX_BYTES or time.monotonic() - self.started > MAX_SECONDS:
                    raise ValueError("Probe response/time budget exhausted")
        raw = bytes(payload)
        (self.folder / entry["file"]).write_bytes(raw)
        entry.update(
            received_at=datetime.now(UTC).isoformat(),
            bytes=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
        )
        self.save()
        return decode(raw)


def capture(folder: Path, client: httpx.Client) -> None:
    probe = Capture(folder, client)
    probe.get("dam-before", DAM)
    for index, (area, (lat, lon)) in enumerate(AREAS.items()):
        probe.get(
            f"weather-{index}",
            WEATHER,
            {
                "latitude": str(lat),
                "longitude": str(lon),
                "current": ",".join(VARIABLES),
                "timezone": "GMT",
                "timeformat": "unixtime",
                "wind_speed_unit": "ms",
                "models": "best_match",
                "forecast_days": "1",
            },
        )
        for offset in range(0, 1000, 100):
            page = probe.get(
                f"dam-{index}-{offset}",
                DAM + "/records",
                {
                    "select": "development_key,status,clue_small_area,geopoint,year_completed",
                    "where": f"clue_small_area='{area}'",
                    "order_by": "development_key",
                    "limit": "100",
                    "offset": str(offset),
                },
            )
            # Validate before using a provider value to control further requests.
            planning_summary([page], area)
            if offset + len(page["results"]) >= page["total_count"]:
                break
            if not page["results"]:
                raise ValueError("Empty page before advertised total")
        time.sleep(1)
    probe.get("dam-after", DAM)
    probe.manifest["complete"] = True
    probe.save()


def replay(folder: Path) -> dict[str, Any]:
    manifest = decode((folder / "manifest.json").read_bytes())
    if manifest.get("schema") != "bounded-source-probe-v1" or manifest.get("complete") is not True:
        raise ValueError("Incomplete probe; retained captures are diagnostic only")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or len(entries) > MAX_REQUESTS:
        raise ValueError("Invalid probe inventory")
    data = {}
    for index, value in enumerate(entries):
        entry = record(value)
        if entry.get("file") != f"{index:02d}.json" or entry.get("name") in data:
            raise ValueError("Invalid capture reference")
        raw = (folder / entry["file"]).read_bytes()
        if len(raw) > MAX_BYTES or hashlib.sha256(raw).hexdigest() != entry.get("sha256"):
            raise ValueError("Capture integrity failure")
        data[entry["name"]] = decode(raw)
    before = record(record(data["dam-before"].get("metas")).get("default"))
    after = record(record(data["dam-after"].get("metas")).get("default"))
    areas = {}
    for index, area in enumerate(AREAS):
        pages = [value for key, value in data.items() if key.startswith(f"dam-{index}-")]
        if not pages:
            raise ValueError("Missing planning pages")
        areas[area] = {
            "weather": weather_summary(data[f"weather-{index}"]),
            "planning": planning_summary(pages, area),
        }
    return {
        "requests": len(entries),
        "payload_bytes": sum(e["bytes"] for e in entries),
        "areas": areas,
        "dam_metadata": {
            k: before.get(k)
            for k in ("modified", "data_processed", "license", "license_url", "records_count")
        },
        "dam_metadata_stable": all(
            before.get(k) == after.get(k) for k in ("modified", "data_processed", "records_count")
        ),
        "public_live_enabled": False,
        "warning_coverage": "not_evaluated",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument(
        "--capture", type=Path, help="New local output directory; at most 16 public GETs"
    )
    choice.add_argument(
        "--replay", type=Path, help="Recompute from retained bytes without network access"
    )
    args = parser.parse_args()
    folder = args.capture or args.replay
    if args.capture:
        with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client:
            capture(folder, client)
    result = replay(folder)
    (folder / "analysis.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

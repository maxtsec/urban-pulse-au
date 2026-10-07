"""Bounded operator-run Transport Victoria research; no application writes or cloud upload."""

import argparse
import gzip
import hashlib
import json
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from dotenv import dotenv_values
from google.protobuf.message import DecodeError  # type: ignore[import-untyped]

from scripts.gtfs_probe import Schedule, decode, entity_fingerprint, positions, summarize

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / ".local" / "src-02-transport"
BASE = "https://api.opendata.transport.vic.gov.au/opendata/public-transport/gtfs/realtime/v1/tram"
HEADERS = ("KeyID", "Ocp-Apim-Subscription-Key")
MAX_BYTES = 8 * 1024 * 1024


def request_plan(duration: int) -> list[tuple[int, str]]:
    if duration not in (60, 120):
        raise ValueError("Probe duration must be 60 or 120 seconds")
    plan = [(s, "vehicle-positions") for s in range(0, duration + 1, 30)]
    plan += [(s + 10, "trip-updates") for s in range(0, duration + 1, 60)]
    plan += [(s + 20, "service-alerts") for s in range(0, duration + 1, 60)]
    return sorted(plan)


def fetch(
    client: httpx.Client, feed: str, key: str, header: str
) -> tuple[dict[str, Any], bytes | None]:
    if feed not in {"vehicle-positions", "trip-updates", "service-alerts"} or header not in HEADERS:
        raise ValueError("Unsupported endpoint/header")
    started = time.monotonic()
    result: dict[str, Any] = {"feed": feed, "requested_at": datetime.now(UTC).isoformat()}
    try:
        # Fixed HTTPS origin; never forward secrets to redirects or put them in URLs.
        with client.stream(
            "GET",
            BASE + "/" + feed,
            headers={header: key, "Accept-Encoding": "identity"},
            follow_redirects=False,
        ) as response:
            result["http_status"] = response.status_code
            if response.status_code != 200:
                result["error"] = "http_error"
                return result, None
            if response.headers.get("content-encoding", "identity").lower() != "identity":
                result["error"] = "unexpected_content_encoding"
                return result, None
            body = bytearray()
            for chunk in response.iter_raw():
                if len(body) + len(chunk) > MAX_BYTES or time.monotonic() - started > 15:
                    result["error"] = "response_limit"
                    return result, None
                body.extend(chunk)
        result["received_at"] = datetime.now(UTC).isoformat()
        result["elapsed_ms"] = round((time.monotonic() - started) * 1000)
        return result, bytes(body)
    except httpx.HTTPError:
        # Exception strings and response bodies may contain credentials or provider echoes.
        result["error"] = "network_error"
        return result, None


def run_probe(
    client: httpx.Client,
    schedule: Schedule,
    key: str,
    header: str,
    output: Path,
    duration: int,
    *,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    plan = request_plan(duration)
    report: dict[str, Any] = {
        "schema": "transport-source-probe-v1",
        "auth_header": header,
        "static": schedule.inventory(),
        "planned_requests": len(plan),
        "captures": [],
        "scope": "tram network; linkage is not spatial shape matching or live enablement",
    }
    start = monotonic()
    previous_start: float | None = None
    previous: dict[str, str] = {}
    previous_entities: dict[str, str] = {}
    previous_positions: dict[str, tuple[Any, ...]] = {}
    for offset, feed in plan:
        # A slow request cannot produce a catch-up burst. One request at a time, >=10s apart.
        target = max(start + offset, previous_start + 10 if previous_start is not None else start)
        sleep(max(0, target - monotonic()))
        if monotonic() - start > duration + 50:
            report["stopped"] = "session_deadline"
            break
        previous_start = monotonic()
        record, body = fetch(client, feed, key, header)
        report["captures"].append(record)
        if body is None:
            report["stopped"] = record["error"]
            break
        index = len(report["captures"])
        name = f"{index:02d}-{feed}.pb"
        (output / name).write_bytes(body)
        digest = hashlib.sha256(body).hexdigest()
        record.update(
            payload=name,
            bytes=len(body),
            sha256=digest,
            gzip_bytes=len(gzip.compress(body, compresslevel=6, mtime=0)),
            unchanged=previous.get(feed) == digest if feed in previous else None,
        )
        previous[feed] = digest
        try:
            parsed = decode(body)
            entity_hash = entity_fingerprint(parsed)
            record["entity_payload_sha256"] = entity_hash
            record["unchanged_entities"] = (
                previous_entities[feed] == entity_hash if feed in previous_entities else None
            )
            previous_entities[feed] = entity_hash
            record["summary"] = summarize(
                parsed, schedule, datetime.fromisoformat(record["received_at"]).timestamp()
            )
            if feed == "vehicle-positions":
                current = positions(parsed)
                shared = current.keys() & previous_positions.keys()
                record["position_comparison"] = {
                    "shared_vehicles": len(shared),
                    "coordinates_changed": sum(
                        current[k][:2] != previous_positions[k][:2] for k in shared
                    ),
                    "coordinates_changed_same_observed_at": sum(
                        current[k][:2] != previous_positions[k][:2]
                        and current[k][2] is not None
                        and current[k][2] == previous_positions[k][2]
                        for k in shared
                    ),
                    "observation_time_changed": sum(
                        current[k][2] != previous_positions[k][2] for k in shared
                    ),
                }
                previous_positions = current
        except (ValueError, DecodeError):
            record["error"] = "invalid_protobuf"
            report["stopped"] = "invalid_protobuf"
            break
        finally:
            (output / "report.json").write_text(
                json.dumps(report, indent=2) + "\n", encoding="utf-8"
            )
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--static-zip",
        type=Path,
        required=True,
        help="Extracted mode-3 GTFS ZIP (not statewide outer ZIP)",
    )
    parser.add_argument(
        "--live", action="store_true", help="Opt into bounded authenticated provider requests"
    )
    parser.add_argument("--header", choices=HEADERS, default="KeyID")
    parser.add_argument("--duration-seconds", type=int, choices=(60, 120), default=60)
    args = parser.parse_args()
    path = args.static_zip if args.static_zip.is_absolute() else ROOT / args.static_zip
    schedule = Schedule.read(path)
    if not args.live:
        print(json.dumps(schedule.inventory(), indent=2))
        return 0
    key = os.environ.get("DTP_OPENDATA_API_KEY") or dotenv_values(ROOT / ".env").get(
        "DTP_OPENDATA_API_KEY"
    )
    if not key:
        parser.error("DTP_OPENDATA_API_KEY is missing; configure it locally without printing it")
    PRIVATE.mkdir(parents=True, exist_ok=True)
    lock = PRIVATE / "probe.lock"
    try:
        handle = lock.open("x", encoding="utf-8")
    except FileExistsError:
        parser.error("Probe lock exists; verify no probe is running before removing a stale lock")
    try:
        with handle:
            handle.write(str(os.getpid()))
        output = PRIVATE / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
        output.mkdir()
        with httpx.Client(timeout=10) as client:
            report = run_probe(client, schedule, key, args.header, output, args.duration_seconds)
        print(
            json.dumps(
                {
                    "report": str(output / "report.json"),
                    "requests": len(report["captures"]),
                    "stopped": report.get("stopped"),
                }
            )
        )
        return 1 if "stopped" in report else 0
    finally:
        lock.unlink()


if __name__ == "__main__":
    raise SystemExit(main())

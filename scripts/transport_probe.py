"""Bounded operator-run Transport Victoria research; no application writes or cloud upload."""

import argparse
import copy
import gzip
import hashlib
import json
import os
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from google.protobuf.message import DecodeError  # type: ignore[import-untyped]
from pydantic import SecretStr
from pydantic_settings import BaseSettings

from scripts.gtfs_probe import Schedule, decode, entity_fingerprint, positions, summarize
from urbanpulse.config import Settings

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / ".local" / "src-02-transport"
BASE = "https://api.opendata.transport.vic.gov.au/opendata/public-transport/gtfs/realtime/v1/tram"
HEADERS = ("KeyID", "Ocp-Apim-Subscription-Key")
MAX_BYTES = 8 * 1024 * 1024


class ProbeSettings(BaseSettings):
    model_config = Settings.model_config
    dtp_opendata_api_key: SecretStr | None = None


def code_provenance() -> dict[str, Any]:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()

    files = [
        "scripts/transport_probe.py",
        "scripts/gtfs_probe.py",
        "urbanpulse/config.py",
        "uv.lock",
    ]
    return {
        "commit": git("rev-parse", "HEAD"),
        "dirty": bool(git("status", "--porcelain")),
        "sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files},
    }


class CaptureAnalysis:
    """One shared implementation for live samples and offline replay, in capture order."""

    def __init__(self, schedule: Schedule) -> None:
        self.schedule = schedule
        self.previous: dict[str, str] = {}
        self.previous_entities: dict[str, str] = {}
        self.previous_positions: dict[str, tuple[Any, ...]] = {}

    def analyze(self, record: dict[str, Any], body: bytes) -> None:
        feed = record["feed"]
        digest = hashlib.sha256(body).hexdigest()
        record.update(
            bytes=len(body),
            sha256=digest,
            gzip_bytes=len(gzip.compress(body, compresslevel=6, mtime=0)),
            unchanged=self.previous.get(feed) == digest if feed in self.previous else None,
        )
        self.previous[feed] = digest
        parsed = decode(body)
        entity_hash = entity_fingerprint(parsed)
        record["entity_payload_sha256"] = entity_hash
        record["unchanged_entities"] = (
            self.previous_entities[feed] == entity_hash if feed in self.previous_entities else None
        )
        self.previous_entities[feed] = entity_hash
        received = datetime.fromisoformat(record["received_at"])
        if received.tzinfo is None:
            raise ValueError("Receipt timestamp requires a timezone")
        record["summary"] = summarize(parsed, self.schedule, received.timestamp())
        if feed == "vehicle-positions":
            current = positions(parsed)
            shared = current.keys() & self.previous_positions.keys()
            record["position_comparison"] = {
                "shared_vehicles": len(shared),
                "coordinates_changed": sum(
                    current[k][:2] != self.previous_positions[k][:2] for k in shared
                ),
                "coordinates_changed_same_observed_at": sum(
                    current[k][:2] != self.previous_positions[k][:2]
                    and current[k][2] is not None
                    and current[k][2] == self.previous_positions[k][2]
                    for k in shared
                ),
                "observation_time_changed": sum(
                    current[k][2] != self.previous_positions[k][2] for k in shared
                ),
            }
            self.previous_positions = current


def replay_report(directory: Path, schedule: Schedule) -> dict[str, Any]:
    """Recompute from original bytes and receipt times without rewriting acquisition evidence."""
    directory = directory.resolve()
    report_path = directory / "report.json"
    if report_path.stat().st_size > MAX_BYTES:
        raise ValueError("Report exceeds probe limit")
    report: dict[str, Any] = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("schema") != "transport-source-probe-v1":
        raise ValueError("Unsupported probe report")
    if report["static"]["sha256"] != schedule.sha256:
        raise ValueError("Static archive hash mismatch")
    captures = report["captures"]
    if not isinstance(captures, list) or len(captures) > 11:
        raise ValueError("Invalid capture count")
    analysis = CaptureAnalysis(schedule)
    result = copy.deepcopy(report)
    result["capture_code"] = report.get("capture_code")  # Legacy capture version is unknown.
    for index, record in enumerate(result["captures"], 1):
        if "payload" not in record:
            if not record.get("error"):
                raise ValueError("Missing capture payload")
            continue
        feed = record["feed"]
        if feed not in {"vehicle-positions", "trip-updates", "service-alerts"}:
            raise ValueError("Unknown capture feed")
        if record["payload"] != f"{index:02d}-{feed}.pb":
            raise ValueError("Invalid capture path")
        payload = (directory / record["payload"]).resolve()
        if not payload.is_relative_to(directory) or payload.stat().st_size > MAX_BYTES:
            raise ValueError("Payload outside directory or exceeds limit")
        body = payload.read_bytes()
        if len(body) != record["bytes"] or hashlib.sha256(body).hexdigest() != record["sha256"]:
            raise ValueError("Capture integrity mismatch")
        for field in (
            "summary",
            "entity_payload_sha256",
            "unchanged_entities",
            "position_comparison",
        ):
            record.pop(field, None)
        try:
            analysis.analyze(record, body)
        except (ValueError, DecodeError):
            if record.get("error") != "invalid_protobuf":
                raise
    result["analysis_code"] = code_provenance()
    return result


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
        "capture_code": code_provenance(),
        "scope": "tram network; linkage is not spatial shape matching or live enablement",
    }
    start = monotonic()
    previous_start: float | None = None
    analysis = CaptureAnalysis(schedule)
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
        record["payload"] = name
        try:
            analysis.analyze(record, body)
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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--replay", type=Path, help="Reanalyze retained report and payloads offline")
    mode.add_argument(
        "--live", action="store_true", help="Opt into bounded authenticated provider requests"
    )
    parser.add_argument("--header", choices=HEADERS, default="KeyID")
    parser.add_argument("--duration-seconds", type=int, choices=(60, 120), default=60)
    args = parser.parse_args()
    path = args.static_zip if args.static_zip.is_absolute() else ROOT / args.static_zip
    schedule = Schedule.read(path)
    if args.replay is not None:
        directory = args.replay if args.replay.is_absolute() else ROOT / args.replay
        report = replay_report(directory, schedule)
        output = directory / "replay.json"
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"report": str(output), "captures": len(report["captures"])}))
        return 1 if "stopped" in report else 0
    if not args.live:
        print(json.dumps(schedule.inventory(), indent=2))
        return 0
    secret = ProbeSettings().dtp_opendata_api_key
    if secret is None or not secret.get_secret_value():
        parser.error("DTP_OPENDATA_API_KEY is missing; configure it locally without printing it")
    key = secret.get_secret_value()
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

"""Finite GTFS Schedule archive Job and offline retained-source inspection."""

import argparse
import json
import re
import signal
import tempfile
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any

import httpx
from google.auth import compute_engine
from google.auth.transport.requests import Request

from urbanpulse.adapters.gtfs_archive import SOURCE_URL, Limits, download, prepare
from urbanpulse.adapters.gtfs_archive_gcs import GcsArchive
from urbanpulse.application.schedule_archive import ArchiveError, publish, timestamp
from workers.job_runtime import supervise


@dataclass(frozen=True)
class ArchiveRequest:
    operation: str
    bucket: str | None
    expected_service_account: str | None
    code_version: str
    source_zip: str | None = None
    provenance: str | None = None
    output: str | None = None
    timeout_seconds: int = 540

    def __post_init__(self) -> None:
        if self.operation not in ("inspect", "seed", "check"):
            raise ValueError("unknown operation")
        if not re.fullmatch(r"[a-zA-Z0-9._-]{1,128}", self.code_version):
            raise ValueError("invalid code version")
        if not 1 <= self.timeout_seconds <= 540:
            raise ValueError("invalid deadline")
        if self.operation == "check" and (self.source_zip or self.provenance):
            raise ValueError("check downloads the current official release")
        if self.operation != "check" and not (self.source_zip and self.provenance):
            raise ValueError("retained source and provenance required")
        if self.operation == "inspect":
            if not self.output or self.bucket or self.expected_service_account:
                raise ValueError("inspection needs output and no cloud target")
        elif (
            self.output
            or not self.bucket
            or not self.expected_service_account
            or re.fullmatch(
                r"[a-z0-9-]+@[a-z0-9-]+\.iam\.gserviceaccount\.com", self.expected_service_account
            )
            is None
        ):
            raise ValueError("explicit bucket and expected keyless identity required")


def retained_provenance(path: Path) -> dict[str, object]:
    if path.stat().st_size > 65536:
        raise ValueError("provenance too large")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("source_url") != SOURCE_URL:
        raise ValueError("invalid provenance source")
    result: dict[str, object] = {}
    for key in ("outer_sha256", "tram_sha256"):
        digest = value.get(key)
        if not isinstance(digest, str) or re.fullmatch(r"[a-f0-9]{64}", digest) is None:
            raise ValueError("expected provenance hashes required")
        result[key] = digest
    ref = value.get("evidence_reference")
    if not isinstance(ref, str) or not 1 <= len(ref) <= 512:
        raise ValueError("evidence reference required")
    downloaded = value.get("original_downloaded_at")
    if downloaded is not None:
        if not isinstance(downloaded, str):
            raise ValueError("invalid original timestamp")
        parsed = datetime.fromisoformat(downloaded.replace("Z", "+00:00"))
        if parsed.utcoffset() is None or parsed > datetime.now(UTC):
            raise ValueError("original timestamp must be past and timezone aware")
        downloaded = parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    for key in ("etag", "last_modified"):
        item = value.get(key)
        if item is not None and (not isinstance(item, str) or len(item) > 1024):
            raise ValueError("invalid provider hint")
        result[key] = item
    return {
        **result,
        "source_url": SOURCE_URL,
        "evidence_reference": ref,
        "original_downloaded_at": downloaded,
        "download_time_unknown": downloaded is None,
    }


def execute(request: ArchiveRequest, deadline: float) -> dict[str, str]:
    # A caller explicitly selects the dedicated metadata identity, never a local SA key.
    credentials: Any = None
    if request.operation != "inspect":
        credentials = compute_engine.Credentials()  # type: ignore[no-untyped-call]
        credentials.refresh(Request())
        if credentials.service_account_email != request.expected_service_account:
            raise ValueError("unexpected runtime identity")
    with tempfile.TemporaryDirectory(prefix="gtfs-archive-") as directory:
        workspace = Path(directory)
        with httpx.Client(timeout=30, follow_redirects=False, trust_env=False) as client:

            def acquire() -> tuple[dict[str, object], dict[str, object]]:
                if request.operation == "check":
                    outer = workspace / "outer.zip"
                    provenance = download(client, outer, deadline, Limits())
                    provenance.update(
                        {"original_downloaded_at": timestamp(), "download_time_unknown": False}
                    )
                else:
                    outer = Path(str(request.source_zip))
                    provenance = retained_provenance(Path(str(request.provenance)))
                inventory = prepare(outer, workspace / "tram.zip", deadline)
                if request.operation != "check":
                    for part in ("outer", "tram"):
                        item = inventory[part]
                        if (
                            not isinstance(item, dict)
                            or item["sha256"] != provenance[part + "_sha256"]
                        ):
                            raise ArchiveError("retained_source_hash_mismatch")
                return inventory, provenance

            if request.operation == "inspect":
                inventory, provenance = acquire()
                destination = Path(str(request.output))
                destination.mkdir(parents=True, exist_ok=False)
                with (destination / "report.incomplete").open("x", encoding="utf-8") as output:
                    json.dump(
                        {
                            "status": "inspected",
                            "inventory": inventory,
                            "provenance": provenance,
                            "code_version": request.code_version,
                        },
                        output,
                        sort_keys=True,
                    )
                (destination / "report.incomplete").replace(destination / "report.json")
                return {
                    "status": "complete",
                    "kind": "gtfs_archive_inspection",
                    "output": str(destination),
                }
            objects = GcsArchive(
                str(request.bucket), lambda: str(credentials.token), deadline, client
            )
            return publish(
                objects,
                workspace,
                acquire,
                code_version=request.code_version,
                mode=request.operation,
            )


def child(request: ArchiveRequest, deadline: float, output: Connection) -> None:
    try:
        result = execute(request, deadline)
    except ArchiveError as error:
        result = {"status": "archive-failed", "reason": str(error)}
    except (ValueError, OSError):
        result = {"status": "invalid-input-or-storage"}
    except Exception:
        result = {"status": "execution-failed"}
    try:
        output.send(result)
    finally:
        output.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("inspect", "seed", "check"))
    parser.add_argument("--bucket")
    parser.add_argument("--expected-service-account")
    parser.add_argument("--code-version", required=True)
    parser.add_argument("--source-zip")
    parser.add_argument("--provenance")
    parser.add_argument("--output")
    parser.add_argument("--timeout-seconds", type=int, default=540)
    try:
        request = ArchiveRequest(**vars(parser.parse_args()))
    except ValueError:
        print(json.dumps({"status": "invalid-configuration"}), flush=True)
        return 2
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda signum, frame: stop.set())
    result = supervise(request, stop, child)
    print(json.dumps(result), flush=True)
    return 0 if result["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())

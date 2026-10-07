"""Linux capture operator commands; finite fixture mode is the default."""

import argparse
import json
import math
import os
import signal
import sys
from datetime import UTC, datetime
from pathlib import Path
from threading import Event

import httpx
from pydantic import SecretStr, ValidationError

from urbanpulse.adapters.capture_checkpoint import CheckpointJournal as CaptureJournal
from urbanpulse.adapters.capture_verify import CaptureVerifier
from urbanpulse.adapters.synthetic_capture import SyntheticCapture
from urbanpulse.adapters.transport_capture import TransportCapture
from urbanpulse.application.local_collector import collect
from urbanpulse.contracts.local_capture import CaptureError, Mode, Source


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "status", "run", "verify"))
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument(
        "--live", action="store_true", help="Requires separately approved source policy"
    )
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--max-attempts", type=int, default=6)
    parser.add_argument("--max-seconds", type=float, default=120)
    parser.add_argument("--interval", type=float)
    args = parser.parse_args()
    if not 1 <= args.max_attempts <= 120 or not 1 <= args.max_seconds <= 3600:
        parser.error("Use 1..120 attempts and 1..3600 seconds")
    mode: Mode = "live" if args.live else "fixture"
    interval = args.interval if args.interval is not None else (15 if args.live else 1)
    if not math.isfinite(interval) or interval < (15 if args.live else 0.01):
        parser.error("Live request spacing must be at least 15 seconds")
    stop = Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    try:
        if args.command == "verify":
            with CaptureVerifier(args.store).locked() as verifier:
                report = verifier.verify(stopped=stop.is_set)
                print(json.dumps(report, sort_keys=True))
                return 0 if report["status"] == "verified" else 1
        with CaptureJournal(args.store).locked(initialize=args.command == "init") as journal:
            summary = journal.recover()
            if args.command != "run":
                print(
                    json.dumps(
                        {
                            "status": "ready"
                            if summary["collection_allowed"]
                            else "verification_required",
                            **summary,
                        },
                        sort_keys=True,
                    )
                )
                return 0 if summary["collection_allowed"] else 2
            if not summary["collection_allowed"]:
                raise CaptureError("verification_required")
            with httpx.Client(trust_env=False) as client:
                source: Source = SyntheticCapture()
                if args.live:
                    if args.key_file is None:
                        raise CaptureError("key_file_required")
                    key = args.key_file.read_text(encoding="utf-8").strip()
                    if not key or len(key) > 1024 or any(ord(c) < 33 or ord(c) > 126 for c in key):
                        raise CaptureError("key_file_invalid")
                    source = TransportCapture(client, SecretStr(key))
                session = journal.start_session(mode, summary)
                attempts: int | None = None
                reason = "execution_failed"
                try:
                    # Empty restart windows cannot bypass the shared quota; longer
                    # server Retry-After deadlines survive restarts in manifests.
                    delay = 60.0 if args.live else 0.0
                    if args.live and summary["retry_not_before"] is not None:
                        delay = max(
                            delay,
                            (
                                datetime.fromisoformat(summary["retry_not_before"])
                                - datetime.now(UTC)
                            ).total_seconds(),
                        )
                    result = collect(
                        journal,
                        source,
                        mode=mode,
                        version=os.environ.get("COLLECTOR_VERSION", "local-capture-v2"),
                        stop=stop,
                        max_attempts=args.max_attempts,
                        max_seconds=args.max_seconds,
                        interval=interval,
                        initial_delay=delay,
                    )
                    attempts, reason = result.attempts, result.reason
                    print(
                        json.dumps(
                            {"status": reason, "attempts": attempts, "captured": result.captured}
                        )
                    )
                    return (
                        1
                        if result.captured < attempts or (attempts == 0 and reason != "stopped")
                        else 0
                    )
                finally:
                    primary_error = sys.exception()
                    try:
                        journal.end_session(session, reason, attempts)
                    except (OSError, CaptureError):
                        if primary_error is None:
                            raise
                        primary_error.add_note("session_end_write_failed")
    except (CaptureError, OSError, ValueError, ValidationError) as error:
        # No arbitrary exception, response body, path, URL or key appears in logs.
        reason = str(error) if isinstance(error, CaptureError) else "local_capture_failed"
        print(json.dumps({"status": "failed", "reason": reason}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

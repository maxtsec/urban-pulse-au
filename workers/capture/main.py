"""Linux capture operator commands; finite fixture mode is the default."""

import argparse
import json
import math
import os
import signal
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from threading import Event

import httpx
from pydantic import SecretStr, ValidationError

from urbanpulse.adapters.capture_checkpoint import CheckpointJournal as CaptureJournal
from urbanpulse.adapters.capture_journal import RESERVE_BYTES
from urbanpulse.adapters.capture_metrics import MonitoringTarget
from urbanpulse.adapters.capture_monitoring import MonitoringSink
from urbanpulse.adapters.capture_runtime import INODE_RESERVE, RuntimeObservation
from urbanpulse.adapters.capture_v3 import V3Journal
from urbanpulse.adapters.capture_v3_verify import V3Verifier
from urbanpulse.adapters.capture_verify import CaptureVerifier
from urbanpulse.adapters.synthetic_capture import SyntheticCapture
from urbanpulse.adapters.transport_capture import TransportCapture
from urbanpulse.application.local_collector import collect
from urbanpulse.contracts.local_capture import CaptureError, Mode, Source


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "status", "run", "serve", "verify"))
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument(
        "--live", action="store_true", help="Requires separately approved source policy"
    )
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--store-version", choices=("v2", "v3"), default="v2")
    parser.add_argument("--max-attempts", type=int, default=6)
    parser.add_argument("--max-seconds", type=float, default=120)
    parser.add_argument("--interval", type=float)
    parser.add_argument(
        "--tram-schedule", action="store_true", help="Use accepted 60/120/60 slots in fixture mode"
    )
    parser.add_argument("--reserve-bytes", type=int, default=RESERVE_BYTES)
    parser.add_argument("--reserve-inodes", type=int, default=INODE_RESERVE)
    parser.add_argument("--monitoring-project")
    parser.add_argument("--monitoring-collector")
    parser.add_argument("--monitoring-service-account")
    parser.add_argument("--monitoring-key-file", type=Path)
    args = parser.parse_args()
    send: Callable[[str], None] = print
    monitoring = (
        args.monitoring_project,
        args.monitoring_collector,
        args.monitoring_service_account,
        args.monitoring_key_file,
    )
    if any(value is not None for value in monitoring):
        if not all(monitoring) or args.command != "serve" or not args.live:
            parser.error("monitoring_requires_live_serve_and_all_four_options")
        try:
            target = MonitoringTarget(
                project=args.monitoring_project,
                collector=args.monitoring_collector,
                service_account=args.monitoring_service_account,
            )
        except ValidationError:
            parser.error("invalid_monitoring_target")
        send = MonitoringSink(target, args.monitoring_key_file)
    if args.reserve_bytes < RESERVE_BYTES or args.reserve_inodes < INODE_RESERVE:
        parser.error("reserve_below_floor")
    if args.command == "serve" and args.store_version != "v3":
        parser.error("continuous_requires_v3")
    if not 1 <= args.max_attempts <= 120 or not 1 <= args.max_seconds <= 3600:
        parser.error("Use 1..120 attempts and 1..3600 seconds")
    if args.command in {"run", "serve"} and args.live and args.store_version != "v3":
        parser.error("live_requires_v3: use a fresh v3 store with --store-version v3")
    mode: Mode = "live" if args.live else "fixture"
    interval = args.interval if args.interval is not None else (15 if args.live else 1)
    if not math.isfinite(interval) or interval < (15 if args.live else 0.01):
        parser.error("Live request spacing must be at least 15 seconds")
    stop = Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    journal_type = V3Journal if args.store_version == "v3" else CaptureJournal
    verifier_type = V3Verifier if args.store_version == "v3" else CaptureVerifier
    try:
        if args.command == "verify":
            with verifier_type(args.store).locked() as verifier:
                report = verifier.verify(stopped=stop.is_set)
                print(json.dumps(report, sort_keys=True))
                return 0 if report["status"] == "verified" else 1
        with journal_type(args.store, reserve_bytes=args.reserve_bytes).locked(
            initialize=args.command == "init"
        ) as journal:
            summary = journal.recover()
            if args.command not in {"run", "serve"}:
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
            observation = RuntimeObservation(
                args.store,
                mode,
                lambda: journal.control.summary,
                reserve_bytes=args.reserve_bytes,
                reserve_inodes=args.reserve_inodes,
                send=send,
            )
            try:
                observation.guard()
            except CaptureError as error:
                if args.command == "serve":
                    observation.pulse(str(error), force=True)
                raise
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
                        tram_schedule=args.live or args.tram_schedule or args.command == "serve",
                        continuous=args.command == "serve",
                        tick=observation.pulse if args.command == "serve" else lambda: None,
                        before_capture=observation.guard,
                        after_capture=observation.completed
                        if args.command == "serve"
                        else lambda *_: None,
                    )
                    attempts, reason = result.attempts, result.reason
                    print(
                        json.dumps(
                            {"status": reason, "attempts": attempts, "captured": result.captured}
                        )
                    )
                    if reason == "source_rejected" and args.command == "serve":
                        return 78
                    return (
                        1
                        if result.captured < attempts or (attempts == 0 and reason != "stopped")
                        else 0
                    )
                except CaptureError as error:
                    reason = str(error)
                    raise
                finally:
                    if args.command == "serve":
                        observation.pulse(reason, force=True)
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
        operator_required = args.command == "serve" and reason in {
            "disk_reserve_reached",
            "inode_reserve_reached",
        }
        print(
            json.dumps(
                {"status": "operator_required" if operator_required else "failed", "reason": reason}
            )
        )
        return 78 if operator_required else 2


if __name__ == "__main__":
    raise SystemExit(main())

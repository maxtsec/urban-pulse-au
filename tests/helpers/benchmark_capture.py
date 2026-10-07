"""Offline capture-startup measurement on a new disposable persistent store."""

import argparse
import hashlib
import json
import platform
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

from urbanpulse.adapters.capture_checkpoint import CheckpointJournal
from urbanpulse.adapters.capture_journal import local_filesystem
from urbanpulse.contracts.local_capture import FetchResult


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", required=True, type=Path)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--dirty", action="store_true")
    parser.add_argument("--counts", nargs="+", type=int, default=[10, 1000])
    args = parser.parse_args()
    if any(n <= 0 or n > 10000 for n in args.counts):
        parser.error("Use 1..10000 captures")
    if any(args.store.iterdir()):
        parser.error("Benchmark requires a new empty dedicated directory")
    payload = b"synthetic-not-gtfs:" + b"x" * (8192 - len(b"synthetic-not-gtfs:"))
    rows = []
    previous = 0
    with CheckpointJournal(args.store).locked(initialize=True):
        pass
    for count in sorted(set(args.counts)):
        with CheckpointJournal(args.store).locked() as journal:
            for _ in range(previous, count):
                intent = journal.begin("fixture", "vehicle-positions", "benchmark")
                now = datetime.now(UTC)
                journal.complete(intent, FetchResult(now, now, 200, payload))
        samples = []
        for _ in range(5):
            started = time.perf_counter_ns()
            with CheckpointJournal(args.store).locked() as journal:
                summary = journal.recover()
            samples.append((time.perf_counter_ns() - started) / 1_000_000)
            if summary["outcomes"]["captured"] != count:
                raise RuntimeError("count_mismatch")
        rows.append(
            {
                "captures": count,
                "payload_bytes": count * len(payload),
                "files": sum(p.is_file() for p in args.store.rglob("*")),
                "startup_ms": samples,
                "median_ms": statistics.median(samples),
            }
        )
        previous = count
    sources = [
        Path("urbanpulse/adapters") / name
        for name in ("capture_journal.py", "capture_checkpoint.py")
    ]
    sources += [Path("urbanpulse/contracts/capture_control.py")]
    print(
        json.dumps(
            {
                "revision": args.revision,
                "dirty": args.dirty,
                "python": platform.python_version(),
                "platform": platform.platform(),
                "filesystem": local_filesystem(args.store),
                "rows": rows,
                "source_sha256": {
                    str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

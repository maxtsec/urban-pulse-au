"""Bounded local capacity checks and best-effort dry-run heartbeat delivery."""

import json
import os
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from urbanpulse.adapters.capture_journal import RESERVE_BYTES
from urbanpulse.contracts.capture_control import Summary
from urbanpulse.contracts.local_capture import MAX_BYTES, CaptureError, Intent, Manifest, Mode

INODE_RESERVE = 4096


def capacity(root: Path) -> tuple[int, int]:
    if sys.platform == "win32":
        raise OSError("linux_capacity_required")
    else:
        value = os.statvfs(root)
        return value.f_bavail * value.f_frsize, value.f_favail


class RuntimeObservation:
    """No archive scan or background healthy pulse while capture is stuck.

    Each attempted send has one bounded-size record. No retry queue is retained.
    The sink must return promptly; authenticated delivery has a separate bounded adapter.
    """

    def __init__(
        self,
        root: Path,
        mode: Mode,
        summary: Callable[[], Summary],
        *,
        reserve_bytes: int = RESERVE_BYTES,
        reserve_inodes: int = INODE_RESERVE,
        read_capacity: Callable[[Path], tuple[int, int]] = capacity,
        send: Callable[[str], None] = lambda line: print(line, flush=True),
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if reserve_bytes < RESERVE_BYTES or reserve_inodes < INODE_RESERVE:
            raise ValueError("reserve_below_floor")
        self.root, self.mode, self.summary = root, mode, summary
        self.reserve_bytes, self.reserve_inodes = reserve_bytes, reserve_inodes
        self.read_capacity, self.send, self.monotonic = read_capacity, send, monotonic
        self.session_id = str(uuid4())
        self.started = monotonic()
        self.next_send = self.started
        self.latest: dict[str, dict[str, str]] = {}
        self.send_failures = 0

    def guard(self) -> None:
        free_bytes, free_inodes = self.read_capacity(self.root)
        if free_bytes < self.reserve_bytes + MAX_BYTES + 65536:
            raise CaptureError("disk_reserve_reached")
        # More than the maximum small-file count of one capture; keep room for
        # session/control cleanup. Never recover space by deleting raw here.
        if free_inodes < self.reserve_inodes + 32:
            raise CaptureError("inode_reserve_reached")

    def completed(self, intent: Intent, manifest: Manifest) -> None:
        self.latest[intent.product] = {"outcome": manifest.outcome}
        self.pulse()

    def pulse(self, state: str = "running", *, force: bool = False) -> None:
        now = self.monotonic()
        if not force and now < self.next_send:
            return
        self.next_send = now + 30
        try:
            free_bytes, free_inodes = self.read_capacity(self.root)
            summary = self.summary()
            record = {
                "kind": "collector_heartbeat_dry_run",
                "session_id": self.session_id,
                "mode": self.mode,
                "state": state,
                "emitted_at": datetime.now(UTC).isoformat(),
                "uptime_seconds": int(max(0, now - self.started)),
                "last_capture_at": {
                    key: value.isoformat()
                    for key, value in summary.last_capture_at.items()
                    if key.startswith(self.mode + "/")
                },
                "session_latest_outcomes": self.latest,
                "free_bytes": free_bytes,
                "free_inodes": free_inodes,
                "send_failures": self.send_failures,
            }
            self.send(json.dumps(record, sort_keys=True))
        except Exception:
            # Telemetry failure must never interrupt an in-flight durable write.
            # Saturate the counter and keep no unbounded failed-message queue.
            self.send_failures = min(self.send_failures + 1, 2**63 - 1)

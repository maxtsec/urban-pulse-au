"""Linux single-writer, create-only capture journal on a local filesystem."""

import hashlib
import json
import os
import shutil
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Self
from uuid import UUID, uuid4

from pydantic import ValidationError

from urbanpulse.contracts.local_capture import (
    MAX_BYTES,
    CaptureError,
    FetchResult,
    Intent,
    Manifest,
    Mode,
    Receipt,
    TramFeed,
)

MARKER = {"schema_version": "capture-store-v1"}
RESERVE_BYTES = 256 * 1024 * 1024


def sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_bytes(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def publish_json(path: Path, value: dict[str, Any]) -> None:
    """Hard-link publication cannot replace existing evidence, even accidentally."""
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if path.exists():
        if path.read_bytes() != data:
            raise CaptureError("integrity_failure")
        return
    temporary = path.with_name(".pending-" + uuid4().hex)
    write_bytes(temporary, data)
    os.link(temporary, path)
    sync_directory(path.parent)
    temporary.unlink()
    sync_directory(path.parent)


def read_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or path.stat().st_size > 16384:
        raise CaptureError("integrity_failure")
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise CaptureError("integrity_failure")
    return value


def local_filesystem(root: Path) -> str:
    """Reject network/foreign mounts; durability still depends on the operator's disk."""
    target = root.resolve()
    matches: list[tuple[int, str]] = []
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        left, right = line.split(" - ", 1)
        mount = left.split()[4]
        for escaped, decoded in ((r"\040", " "), (r"\011", "\t"), (r"\012", "\n"), (r"\134", "\\")):
            mount = mount.replace(escaped, decoded)
        if target.is_relative_to(Path(mount)):
            matches.append((len(mount), right.split()[0]))
    if not matches:
        raise CaptureError("unsupported_filesystem")
    filesystem = max(matches)[1]
    if filesystem not in {"ext4", "xfs", "btrfs"}:
        raise CaptureError("unsupported_filesystem")
    return filesystem


class CaptureJournal:
    def __init__(
        self,
        root: Path,
        *,
        reserve_bytes: int = RESERVE_BYTES,
        checkpoint: Callable[[str], None] = lambda _: None,
    ) -> None:
        self.root = root
        self.reserve_bytes = max(RESERVE_BYTES, reserve_bytes)
        self.checkpoint = checkpoint
        self._locked = False

    @contextmanager
    def locked(self, *, initialize: bool = False) -> Iterator[Self]:
        if sys.platform != "linux":
            raise CaptureError("linux_local_filesystem_required")
        import fcntl

        if not self.root.is_dir() or self.root.is_symlink():
            raise CaptureError("store_missing")
        local_filesystem(self.root)
        lock_path = self.root / ".collector.lock"
        if lock_path.is_symlink():
            raise CaptureError("integrity_failure")
        with lock_path.open("a+b") as stream:
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise CaptureError("collector_already_running") from None
            self._locked = True
            try:
                self._open_store(initialize)
                yield self
            finally:
                self._locked = False
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def _open_store(self, initialize: bool) -> None:
        marker = self.root / "store.json"
        if initialize and not marker.exists():
            # Never initialize over an unknown store or lost marker.
            if any(p.name != ".collector.lock" for p in self.root.iterdir()):
                raise CaptureError("store_not_empty")
            publish_json(marker, MARKER)
        if not marker.exists() or read_json(marker) != MARKER:
            raise CaptureError("store_marker_invalid")
        for name in ("captures", "sessions"):
            path = self.root / name
            if path.is_symlink():
                raise CaptureError("integrity_failure")
            path.mkdir(exist_ok=True)
        sync_directory(self.root)

    def _require_lock(self) -> None:
        if not self._locked:
            raise CaptureError("store_lock_required")

    def _capture(self, capture_id: UUID) -> Path:
        path = self.root / "captures" / str(capture_id)
        if path.is_symlink():
            raise CaptureError("integrity_failure")
        return path

    def begin(self, mode: Mode, feed: TramFeed, version: str) -> Intent:
        self._require_lock()
        if shutil.disk_usage(self.root).free < self.reserve_bytes + MAX_BYTES + 65536:
            raise CaptureError("disk_reserve_reached")
        intent = Intent(
            capture_id=uuid4(),
            mode=mode,
            provider="synthetic" if mode == "fixture" else "transport-victoria",
            product=feed,
            requested_at=datetime.now(UTC),
            collector_version=version,
        )
        directory = self._capture(intent.capture_id)
        directory.mkdir()
        sync_directory(directory.parent)
        self.checkpoint("capture_directory")
        publish_json(directory / "intent.json", intent.model_dump(mode="json"))
        self.checkpoint("intent")
        return intent

    def _receipt(self, directory: Path, intent: Intent) -> Receipt:
        response = directory / "response"
        if response.is_symlink() or (response / "payload.bin").is_symlink():
            raise CaptureError("integrity_failure")
        receipt = Receipt.model_validate(read_json(response / "receipt.json"))
        payload = response / "payload.bin"
        if (
            receipt.capture_id != intent.capture_id
            or receipt.requested_at < intent.requested_at
            or receipt.received_at < receipt.requested_at
            or payload.stat().st_size != receipt.byte_length
            or hashlib.sha256(payload.read_bytes()).hexdigest() != receipt.sha256
        ):
            raise CaptureError("integrity_failure")
        return receipt

    def _terminal(self, directory: Path, manifest: Manifest) -> Manifest:
        publish_json(directory / "manifest.json", manifest.model_dump(mode="json"))
        self.checkpoint("manifest")
        return manifest

    def complete(self, intent: Intent, result: FetchResult) -> Manifest:
        self._require_lock()
        directory = self._capture(intent.capture_id)
        if Intent.model_validate(read_json(directory / "intent.json")) != intent:
            raise CaptureError("integrity_failure")
        manifest_path = directory / "manifest.json"
        if manifest_path.exists():
            prior = Manifest.model_validate(read_json(manifest_path))
            expected = "captured" if result.payload is not None else "fetch-failed"
            if prior.outcome != expected:
                raise CaptureError("integrity_failure")
        if result.payload is None:
            if (directory / "response").exists():
                raise CaptureError("integrity_failure")
            return self._terminal(
                directory,
                Manifest(
                    capture_id=intent.capture_id,
                    outcome="fetch-failed",
                    completed_at=result.received_at,
                    reason=result.reason or "network_error",
                    http_status=result.http_status,
                    retry_not_before=(
                        result.received_at + timedelta(seconds=result.retry_after_seconds)
                    )
                    if result.retry_after_seconds is not None
                    else None,
                ),
            )
        if result.http_status != 200 or result.reason is not None:
            raise CaptureError("invalid_fetch_result")
        receipt = Receipt(
            capture_id=intent.capture_id,
            requested_at=result.requested_at,
            received_at=result.received_at,
            content_type=result.content_type,
            byte_length=len(result.payload),
            sha256=hashlib.sha256(result.payload).hexdigest(),
        )
        if receipt.requested_at < intent.requested_at or receipt.received_at < receipt.requested_at:
            raise CaptureError("invalid_fetch_result")
        try:
            if not (directory / "response").exists():
                staging = directory / (".response-" + uuid4().hex)
                staging.mkdir()
                write_bytes(staging / "payload.bin", result.payload)
                self.checkpoint("payload")
                write_bytes(staging / "receipt.json", receipt.model_dump_json().encode())
                sync_directory(staging)
                self.checkpoint("receipt")
                staging.rename(directory / "response")
                sync_directory(directory)
                self.checkpoint("response")
            if self._receipt(directory, intent) != receipt:
                raise CaptureError("integrity_failure")
            return self._terminal(
                directory,
                Manifest(
                    capture_id=intent.capture_id,
                    outcome="captured",
                    completed_at=receipt.received_at,
                    http_status=200,
                    receipt=receipt,
                ),
            )
        except OSError:
            # A published response is recoverable. Do not contradict it with a failure.
            if not (directory / "response").exists():
                try:
                    self._terminal(
                        directory,
                        Manifest(
                            capture_id=intent.capture_id,
                            outcome="raw-write-failed",
                            completed_at=datetime.now(UTC),
                            reason="storage_error",
                            http_status=200,
                        ),
                    )
                except OSError:
                    pass
            raise CaptureError("storage_error") from None

    def recover(self) -> dict[str, Any]:
        """Full integrity scan before polling. Never fetches or deletes source evidence."""
        self._require_lock()
        counts = dict.fromkeys(("captured", "fetch-failed", "raw-write-failed", "abandoned"), 0)
        latest: dict[str, str] = {}
        orphan_directories = 0
        retry_not_before: str | None = None
        try:
            for directory in sorted((self.root / "captures").iterdir()):
                identity = UUID(directory.name)
                if directory.is_symlink() or not directory.is_dir():
                    raise CaptureError("integrity_failure")
                if not (directory / "intent.json").exists():
                    # No request can have started without a published intent.
                    if any(not p.name.startswith(".pending-") for p in directory.iterdir()):
                        raise CaptureError("integrity_failure")
                    orphan_directories += 1
                    continue
                intent = Intent.model_validate(read_json(directory / "intent.json"))
                if intent.capture_id != identity:
                    raise CaptureError("integrity_failure")
                receipt = (
                    self._receipt(directory, intent) if (directory / "response").exists() else None
                )
                manifest_path = directory / "manifest.json"
                if manifest_path.exists():
                    manifest = Manifest.model_validate(read_json(manifest_path))
                    if (
                        manifest.capture_id != identity
                        or manifest.receipt != receipt
                        or (manifest.outcome == "captured") != (receipt is not None)
                        or (
                            receipt is not None
                            and (
                                manifest.completed_at != receipt.received_at
                                or manifest.http_status != 200
                                or manifest.reason is not None
                            )
                        )
                    ):
                        raise CaptureError("integrity_failure")
                elif receipt is not None:
                    manifest = self._terminal(
                        directory,
                        Manifest(
                            capture_id=identity,
                            outcome="captured",
                            completed_at=receipt.received_at,
                            http_status=200,
                            receipt=receipt,
                        ),
                    )
                else:
                    manifest = self._terminal(
                        directory,
                        Manifest(
                            capture_id=identity,
                            outcome="abandoned",
                            completed_at=datetime.now(UTC),
                            reason="interrupted",
                        ),
                    )
                counts[manifest.outcome] += 1
                if intent.mode == "live" and manifest.retry_not_before is not None:
                    instant = manifest.retry_not_before.astimezone(UTC).isoformat()
                    retry_not_before = max(retry_not_before or instant, instant)
                if receipt is not None:
                    key = intent.mode + "/" + intent.product
                    instant = receipt.received_at.astimezone(UTC).isoformat()
                    latest[key] = max(latest.get(key, instant), instant)
        except (OSError, ValueError, ValidationError):
            raise CaptureError("integrity_failure") from None
        return {
            "outcomes": counts,
            "last_capture_at": latest,
            "orphan_directories": orphan_directories,
            "retry_not_before": retry_not_before,
        }

    def start_session(self, mode: Mode, summary: dict[str, Any]) -> UUID:
        self._require_lock()
        identity = uuid4()
        publish_json(
            self.root / "sessions" / (str(identity) + ".start.json"),
            {
                "schema_version": "capture-session-v1",
                "session_id": str(identity),
                "started_at": datetime.now(UTC).isoformat(),
                "mode": mode,
                "previous_capture_at": summary["last_capture_at"],
            },
        )
        return identity

    def end_session(self, identity: UUID, reason: str, attempts: int | None) -> None:
        self._require_lock()
        publish_json(
            self.root / "sessions" / (str(identity) + ".end.json"),
            {
                "schema_version": "capture-session-v1",
                "session_id": str(identity),
                "ended_at": datetime.now(UTC).isoformat(),
                "reason": reason,
                "attempts": attempts,
            },
        )

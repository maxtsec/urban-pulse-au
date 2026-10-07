"""Offline historical integrity inspection, separate from bounded capture recovery."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from urbanpulse.adapters.capture_checkpoint import CheckpointJournal, inspect_capture, replace_json
from urbanpulse.adapters.capture_journal import MARKER, read_json, sync_directory
from urbanpulse.contracts.capture_control import Summary
from urbanpulse.contracts.local_capture import CaptureError


class CaptureVerifier(CheckpointJournal):
    """Own the same OS lock; never reconcile or rewrite capture evidence."""

    legacy = False

    def _open_store(self, initialize: bool) -> None:
        value = read_json(self.root / "store.json")
        self.legacy = value == MARKER
        if not self.legacy:
            super()._open_store(False)
        else:
            for name in ("captures", "sessions"):
                path = self.root / name
                if path.is_symlink() or not path.is_dir():
                    raise CaptureError("integrity_failure")

    def verify(self, *, stopped: Callable[[], bool] = lambda: False) -> dict[str, Any]:
        self._require_lock()
        record: dict[str, Any] = {}
        if not self.legacy:
            record = {
                "schema_version": "capture-verification-v1",
                "store_id": str(self.control.store_id),
                "verification_id": str(uuid4()),
                "generation": self.control.generation,
                "started_at": datetime.now(UTC).isoformat(),
            }
            replace_json(
                self.root / "verification-in-progress.json",
                record,
                checkpoint=self.checkpoint,
                stage="verify_progress",
            )
            self.checkpoint("verify_started")
        try:
            report = self._scan(stopped)
        except (CaptureError, OSError, ValueError) as error:
            if not self.legacy and str(error) != "verification_interrupted":
                replace_json(
                    self.root / "verification-block.json",
                    {**record, "reason": "integrity_failure"},
                    checkpoint=self.checkpoint,
                    stage="verify_failure",
                )
                self.checkpoint("verify_failed")
            if isinstance(error, CaptureError):
                raise
            raise CaptureError("integrity_failure") from None
        if not self.legacy:
            report = {**record, **report, "completed_at": datetime.now(UTC).isoformat()}
            replace_json(
                self.root / "last-verification.json",
                report,
                checkpoint=self.checkpoint,
                stage="verify_result",
            )
            self.checkpoint("verify_report")
            for name in ("verification-in-progress.json", "verification-block.json"):
                (self.root / name).unlink(missing_ok=True)
                sync_directory(self.root)
                self.checkpoint("verify_removed_" + name)
        return report

    def _scan(self, stopped: Callable[[], bool]) -> dict[str, Any]:
        summary = Summary()
        sequences: set[int] = set()
        captures = payload_bytes = incomplete = 0
        pending = None if self.legacy else self.control.pending
        pending_seen = False
        for directory in (self.root / "captures").iterdir():
            if stopped():
                raise CaptureError("verification_interrupted")
            identity = UUID(directory.name)
            if directory.is_symlink() or not directory.is_dir():
                raise CaptureError("integrity_failure")
            if self.legacy and not (directory / "intent.json").exists():
                if any(not p.name.startswith(".pending-") for p in directory.iterdir()):
                    raise CaptureError("integrity_failure")
                incomplete += 1
                continue
            intent, receipt, manifest = inspect_capture(self, directory)
            if not self.legacy:
                sequence = intent.capture_sequence
                if sequence is None or sequence in sequences:
                    raise CaptureError("integrity_failure")
                sequences.add(sequence)
            captures += 1
            payload_bytes += receipt.byte_length if receipt else 0
            if pending is not None and identity == pending.capture_id:
                if intent != pending:
                    raise CaptureError("pending_identity_conflict")
                pending_seen = True
                # A pending manifest may be complete but not yet accounted.
            elif manifest is not None:
                summary = summary.include(intent, manifest)
            elif self.legacy:
                incomplete += 1
            else:
                raise CaptureError("integrity_failure")
            self.checkpoint("verify_capture")
        if stopped():
            raise CaptureError("verification_interrupted")
        if not self.legacy:
            if pending is not None and not pending_seen:
                if pending.capture_sequence is None or pending.capture_sequence in sequences:
                    raise CaptureError("integrity_failure")
                sequences.add(pending.capture_sequence)
                incomplete += 1
            expected = self.control.next_capture_sequence - 1
            if (
                len(sequences) != expected
                or (sequences and (min(sequences) != 1 or max(sequences) != expected))
                or summary != self.control.summary
            ):
                raise CaptureError("integrity_failure")
        return {
            "status": "verified" if incomplete == 0 else "incomplete",
            "integrity_scope": "full-published-capture-history",
            "captures": captures,
            "payload_bytes": payload_bytes,
            "incomplete": incomplete,
            **summary.model_dump(mode="json"),
        }

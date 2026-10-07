"""V2 single-pending journal: ordinary recovery never scans completed history."""

import hashlib
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from urbanpulse.adapters.capture_journal import (
    CaptureJournal,
    publish_json,
    read_json,
    sync_directory,
    write_bytes,
)
from urbanpulse.contracts.capture_control import MAX_SEQUENCE, Control, canonical
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


def replace_json(path: Path, value: dict[str, Any]) -> None:
    data = canonical(value)
    if len(data) > 16384 or path.is_symlink():
        raise CaptureError("control_invalid")
    temporary = path.with_name(".control-" + uuid4().hex)
    write_bytes(temporary, data)
    os.replace(temporary, path)
    sync_directory(path.parent)


def inspect_capture(
    journal: CaptureJournal, directory: Path
) -> tuple[Intent, Receipt | None, Manifest | None]:
    """Inspect published bytes without reconciling or changing outcomes."""
    if directory.is_symlink() or not directory.is_dir():
        raise CaptureError("integrity_failure")
    for entry in directory.iterdir():
        if entry.name not in {
            "intent.json",
            "manifest.json",
            "response",
        } and not entry.name.startswith((".pending-", ".response-")):
            raise CaptureError("integrity_failure")
    response = directory / "response"
    if response.exists() and {p.name for p in response.iterdir()} != {
        "payload.bin",
        "receipt.json",
    }:
        raise CaptureError("integrity_failure")
    intent = Intent.model_validate(read_json(directory / "intent.json"))
    if str(intent.capture_id) != directory.name:
        raise CaptureError("integrity_failure")
    receipt = journal._receipt(directory, intent) if (directory / "response").exists() else None
    manifest_path = directory / "manifest.json"
    manifest = Manifest.model_validate(read_json(manifest_path)) if manifest_path.exists() else None
    if manifest is not None and (
        manifest.capture_id != intent.capture_id
        or manifest.receipt != receipt
        or (manifest.outcome == "captured") != (receipt is not None)
        or manifest.completed_at < intent.requested_at
        or (receipt is not None and manifest.completed_at != receipt.received_at)
    ):
        raise CaptureError("integrity_failure")
    return intent, receipt, manifest


class CheckpointJournal(CaptureJournal):
    control: Control

    def _open_store(self, initialize: bool) -> None:
        marker = self.root / "store.json"
        if initialize and not marker.exists():
            if any(p.name != ".collector.lock" for p in self.root.iterdir()):
                raise CaptureError("store_not_empty")
            identity = uuid4()
            for name in ("captures", "sessions", "staging"):
                (self.root / name).mkdir()
            sync_directory(self.root)
            self.control = Control(store_id=identity)
            self._save_control(self.control, "initialize")
            publish_json(marker, {"schema_version": "capture-store-v2", "store_id": str(identity)})
            self.checkpoint("store_marker")
        if not marker.exists():
            raise CaptureError("store_marker_invalid")
        value = read_json(marker)
        if value.get("schema_version") == "capture-store-v1":
            raise CaptureError("store_version_requires_fresh_v2")
        if (
            set(value) != {"schema_version", "store_id"}
            or value["schema_version"] != "capture-store-v2"
        ):
            raise CaptureError("store_marker_invalid")
        try:
            self.store_id = UUID(str(value["store_id"]))
        except ValueError:
            raise CaptureError("store_marker_invalid") from None
        self.control = self._load_control()
        for name in ("captures", "sessions", "staging"):
            path = self.root / name
            if path.is_symlink() or not path.is_dir():
                raise CaptureError("integrity_failure")

    def _load_control(self) -> Control:
        try:
            document = read_json(self.root / "control.json")
            checksum = document.pop("checksum")
            if hashlib.sha256(canonical(document)).hexdigest() != checksum:
                raise ValueError("checksum")
            control = Control.model_validate(document)
            if control.store_id != self.store_id:
                raise ValueError("store_identity")
            return control
        except (OSError, ValueError, KeyError):
            raise CaptureError("control_invalid") from None

    def _save_control(self, control: Control, stage: str) -> None:
        self._require_lock()
        data = canonical(control.document())
        if len(data) > 16384:
            raise CaptureError("control_invalid")
        target = self.root / "control.json"
        if target.is_symlink():
            raise CaptureError("control_invalid")
        temporary = self.root / (".control-" + uuid4().hex)
        write_bytes(temporary, data)
        self.checkpoint(stage + "_written")
        os.replace(temporary, target)
        self.checkpoint(stage + "_replaced")
        sync_directory(self.root)
        self.checkpoint(stage + "_synced")
        self.control = control

    def _not_blocked(self) -> None:
        if (self.root / "verification-block.json").exists() or (
            self.root / "verification-block.json"
        ).is_symlink():
            raise CaptureError("verification_required")

    def _publish_intent(self, intent: Intent, *, not_started: bool = False) -> None:
        directory = self._capture(intent.capture_id)
        # All unpublished metadata is retained separately; a published directory
        # always contains the intent, and reconstructed intents also the outcome.
        staging = self.root / "staging" / str(uuid4())
        staging.mkdir()
        sync_directory(staging.parent)
        publish_json(staging / "intent.json", intent.model_dump(mode="json"))
        if not_started:
            publish_json(
                staging / "manifest.json",
                Manifest(
                    capture_id=intent.capture_id,
                    outcome="abandoned",
                    reason="not_started",
                    completed_at=datetime.now(UTC),
                ).model_dump(mode="json"),
            )
        self.checkpoint("reconstruct_written" if not_started else "intent_written")
        if directory.exists():
            # An existing published directory with no intent is corruption: v2
            # never publishes an empty capture directory.
            raise CaptureError("integrity_failure")
        staging.rename(directory)
        self.checkpoint("reconstruct_replaced" if not_started else "intent_replaced")
        sync_directory(directory.parent)
        sync_directory(staging.parent)
        self.checkpoint("reconstruct_synced" if not_started else "intent")

    def begin(self, mode: Mode, feed: TramFeed, version: str) -> Intent:
        self._require_lock()
        self._not_blocked()
        if self.control.pending is not None:
            raise CaptureError("pending_recovery_required")
        if self.control.next_capture_sequence >= MAX_SEQUENCE:
            raise CaptureError("capture_sequence_exhausted")
        if shutil.disk_usage(self.root).free < self.reserve_bytes + MAX_BYTES + 65536:
            raise CaptureError("disk_reserve_reached")
        intent = Intent(
            capture_id=uuid4(),
            capture_sequence=self.control.next_capture_sequence,
            mode=mode,
            provider="synthetic" if mode == "fixture" else "transport-victoria",
            product=feed,
            requested_at=datetime.now(UTC),
            collector_version=version,
        )
        control = Control(
            store_id=self.control.store_id,
            generation=self.control.generation + 1,
            next_capture_sequence=self.control.next_capture_sequence + 1,
            pending=intent,
            summary=self.control.summary,
        )
        self._save_control(control, "reserve")
        self._publish_intent(intent)
        return intent

    def _account(self, intent: Intent, manifest: Manifest) -> None:
        if self.control.pending != intent:
            raise CaptureError("pending_identity_conflict")
        self._save_control(
            Control(
                store_id=self.control.store_id,
                generation=self.control.generation + 1,
                next_capture_sequence=self.control.next_capture_sequence,
                summary=self.control.summary.include(intent, manifest),
            ),
            "finalize",
        )

    def complete(self, intent: Intent, result: FetchResult) -> Manifest:
        self._require_lock()
        self._not_blocked()
        if self.control.pending is not None and self.control.pending != intent:
            raise CaptureError("pending_identity_conflict")
        if self.control.pending is None:
            if (
                intent.capture_sequence is None
                or intent.capture_sequence >= self.control.next_capture_sequence
            ):
                raise CaptureError("pending_identity_conflict")
            # A retry of a completed write validates those exact retained bytes.
            _, _, previous = inspect_capture(self, self._capture(intent.capture_id))
            if previous is None:
                raise CaptureError("integrity_failure")
        manifest = super().complete(intent, result)
        if self.control.pending is not None:
            self._account(intent, manifest)
        return manifest

    def recover(self) -> dict[str, Any]:
        self._require_lock()
        self.control = self._load_control()
        blocked = (self.root / "verification-block.json").exists() or (
            self.root / "verification-block.json"
        ).is_symlink()
        verification: dict[str, Any] | None = None
        previous_report = self.root / "last-verification.json"
        if previous_report.exists() or previous_report.is_symlink():
            verification = read_json(previous_report)
            if verification.get("store_id") != str(self.control.store_id):
                raise CaptureError("integrity_failure")
        recovered: str | None = None
        if self.control.pending is not None and not blocked:
            intent = self.control.pending
            directory = self._capture(intent.capture_id)
            try:
                if not directory.exists():
                    self._publish_intent(intent, not_started=True)
                stored, receipt, manifest = inspect_capture(self, directory)
                if stored != intent:
                    raise CaptureError("pending_identity_conflict")
                if manifest is None:
                    manifest = self._terminal(
                        directory,
                        Manifest(
                            capture_id=intent.capture_id,
                            outcome="captured" if receipt is not None else "abandoned",
                            completed_at=receipt.received_at if receipt else datetime.now(UTC),
                            reason=None if receipt else "interrupted",
                            http_status=200 if receipt else None,
                            receipt=receipt,
                        ),
                    )
                self._account(intent, manifest)
                recovered = str(intent.capture_id)
            except (OSError, ValueError):
                raise CaptureError("integrity_failure") from None
        return {
            **self.control.summary.model_dump(mode="json"),
            "store_id": str(self.control.store_id),
            "next_capture_sequence": self.control.next_capture_sequence,
            "integrity_scope": "checkpoint-and-pending",
            "orphan_directories": None,
            "recovered_capture": recovered,
            "collection_allowed": not blocked,
            "last_verification": verification,
            "verification": "failed"
            if blocked
            else (
                "interrupted"
                if (self.root / "verification-in-progress.json").exists()
                else "not_checked"
            ),
        }

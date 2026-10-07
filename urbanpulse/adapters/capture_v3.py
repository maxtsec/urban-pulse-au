"""V3 downstream ledger on the existing exclusive, durable capture journal."""

import hashlib
import os
from datetime import timedelta
from pathlib import Path
from typing import TypeVar
from uuid import UUID, uuid4

from urbanpulse.adapters.capture_checkpoint import CheckpointJournal, inspect_capture, replace_json
from urbanpulse.adapters.capture_journal import read_json, sync_directory, write_bytes
from urbanpulse.contracts.capture_control import canonical
from urbanpulse.contracts.capture_delivery import (
    CaptureReference,
    DeliveryRecord,
    ExpiryCompletion,
    ExpiryIntent,
    NormalizationCursor,
    NormalizationRecord,
    NormalizationScope,
    RetentionPolicy,
    UploadConfirmation,
    UploadPending,
)
from urbanpulse.contracts.local_capture import CaptureError, Intent, Manifest, Receipt

T = TypeVar("T", bound=DeliveryRecord)


class V3Journal(CheckpointJournal):
    store_version = "capture-store-v3"
    store_directories = (
        *CheckpointJournal.store_directories,
        "normalization",
        "uploads",
        "confirmations",
        "expiry",
        "policies",
    )

    def _inspect_capture(self, directory: Path) -> tuple[Intent, Receipt | None, Manifest | None]:
        return inspect_capture(self, directory, payload_optional=True)

    def _read(self, path: Path, model: type[T]) -> T:
        try:
            return model.model_validate(read_json(path))
        except (OSError, ValueError):
            raise CaptureError("delivery_record_invalid") from None

    def _publish(self, path: Path, record: DeliveryRecord, stage: str) -> None:
        self._require_lock()
        self._not_blocked()
        # Revalidate even if an in-memory caller mutated a nested mapping.
        record = type(record).model_validate(record.model_dump())
        data = canonical(record.model_dump(mode="json"))
        if len(data) > 16384 or path.is_symlink():
            raise CaptureError("delivery_record_invalid")
        if path.exists():
            if path.read_bytes() != data:
                raise CaptureError("delivery_record_conflict")
            sync_directory(path.parent)
            return
        temporary = path.with_name(".pending-" + uuid4().hex)
        write_bytes(temporary, data)
        self.checkpoint(stage + "_written")
        os.link(temporary, path)
        self.checkpoint(stage + "_linked")
        sync_directory(path.parent)
        self.checkpoint(stage + "_synced")
        temporary.unlink()
        sync_directory(path.parent)
        self.checkpoint(stage + "_cleaned")

    def reference(self, sequence: int) -> tuple[CaptureReference, Manifest]:
        """Resolve finalized capture metadata without hashing or requiring retained raw."""
        self._require_lock()
        finalized = self.control.next_capture_sequence - 1 - int(self.control.pending is not None)
        if sequence > finalized:
            raise CaptureError("capture_not_finalized")
        index = read_json(self._sequence_entry(sequence))
        identity = UUID(str(index["capture_id"]))
        directory = self._capture(identity)
        intent = Intent.model_validate(read_json(directory / "intent.json"))
        self._check_index(intent)
        manifest = Manifest.model_validate(read_json(directory / "manifest.json"))
        receipt = manifest.receipt
        if (
            intent.capture_sequence != sequence
            or intent.capture_id != identity
            or manifest.capture_id != identity
            or manifest.completed_at < intent.requested_at
        ):
            raise CaptureError("delivery_capture_mismatch")
        if receipt is not None:
            response = directory / "response"
            if (
                response.is_symlink()
                or Receipt.model_validate(read_json(response / "receipt.json")) != receipt
            ):
                raise CaptureError("delivery_capture_mismatch")
            if (
                receipt.capture_id != identity
                or receipt.requested_at < intent.requested_at
                or receipt.received_at < receipt.requested_at
                or manifest.completed_at != receipt.received_at
            ):
                raise CaptureError("delivery_capture_mismatch")
        return CaptureReference(
            store_id=self.store_id,
            capture_id=identity,
            sequence=sequence,
            receipt_sha256=hashlib.sha256(canonical(receipt.model_dump(mode="json"))).hexdigest()
            if receipt is not None
            else None,
        ), manifest

    def _check_reference(self, reference: CaptureReference) -> Manifest:
        actual, manifest = self.reference(reference.sequence)
        if actual != reference:
            raise CaptureError("delivery_capture_mismatch")
        return manifest

    def _scope_directory(self, scope: NormalizationScope) -> Path:
        return self._scope_id_directory(scope.digest())

    def _scope_id_directory(self, scope_id: str) -> Path:
        if len(scope_id) != 64 or any(c not in "0123456789abcdef" for c in scope_id):
            raise CaptureError("invalid_scope")
        directory = self.root / "normalization" / scope_id
        if directory.is_symlink():
            raise CaptureError("delivery_record_invalid")
        return directory

    def initialize_scope(self, scope: NormalizationScope) -> None:
        self._require_lock()
        self._not_blocked()
        directory = self._scope_directory(scope)
        if directory.exists():
            self.cursor(scope)
            return
        temporary = self.root / "staging" / (".scope-" + uuid4().hex)
        temporary.mkdir()
        (temporary / "records").mkdir()
        cursor = NormalizationCursor(store_id=self.store_id, scope=scope)
        write_bytes(temporary / "cursor.json", canonical(cursor.document()))
        sync_directory(temporary / "records")
        sync_directory(temporary)
        self.checkpoint("scope_written")
        temporary.rename(directory)
        self.checkpoint("scope_published")
        sync_directory(directory.parent)
        sync_directory(temporary.parent)
        self.checkpoint("scope_synced")

    def cursor(self, scope: NormalizationScope) -> NormalizationCursor:
        self._require_lock()
        directory = self._scope_directory(scope)
        if (directory / "records").is_symlink() or not (directory / "records").is_dir():
            raise CaptureError("delivery_record_invalid")
        try:
            document = read_json(directory / "cursor.json")
            checksum = document.pop("checksum")
            cursor = NormalizationCursor.model_validate(document)
            if (
                cursor.digest() != checksum
                or cursor.store_id != self.store_id
                or cursor.scope != scope
            ):
                raise ValueError("cursor_identity")
            if cursor.through_sequence:
                record = self._normalization(scope.digest(), cursor.through_sequence)
                self._validate_normalization(record)
                if record.digest() != cursor.record_sha256:
                    raise ValueError("cursor_reference")
            return cursor
        except (OSError, ValueError, KeyError):
            raise CaptureError("normalization_cursor_invalid") from None

    def _normalization(self, scope_id: str, sequence: int) -> NormalizationRecord:
        directory = self._scope_id_directory(scope_id) / "records"
        if directory.is_symlink():
            raise CaptureError("delivery_record_invalid")
        path = directory / f"{sequence:019d}.json"
        record = self._read(path, NormalizationRecord)
        if record.scope.digest() != scope_id or record.capture.sequence != sequence:
            raise CaptureError("normalization_identity_mismatch")
        return record

    def pending(self, object_id: str) -> UploadPending:
        if len(object_id) != 64 or any(c not in "0123456789abcdef" for c in object_id):
            raise CaptureError("invalid_object_id")
        pending = self._read(self.root / "uploads" / (object_id + ".json"), UploadPending)
        if pending.object_id() != object_id or pending.store_id != self.store_id:
            raise CaptureError("upload_identity_mismatch")
        for reference in pending.captures:
            self._check_reference(reference)
        return pending

    def publish_pending(self, pending: UploadPending) -> None:
        if pending.store_id != self.store_id:
            raise CaptureError("upload_identity_mismatch")
        for reference in pending.captures:
            self._check_reference(reference)
        self._publish(self.root / "uploads" / (pending.object_id() + ".json"), pending, "upload")

    def _validate_normalization(self, record: NormalizationRecord) -> None:
        manifest = self._check_reference(record.capture)
        if record.completed_at < manifest.completed_at:
            raise CaptureError("normalization_time_invalid")
        for object_id in record.object_ids:
            if record.capture not in self.pending(object_id).captures:
                raise CaptureError("normalization_upload_mismatch")

    def publish_normalization(self, record: NormalizationRecord) -> None:
        self._require_lock()
        self._not_blocked()
        self._validate_normalization(record)
        cursor = self.cursor(record.scope)
        if record.capture.sequence > cursor.through_sequence + 1:
            raise CaptureError("normalization_sequence_gap")
        path = (
            self._scope_directory(record.scope) / "records" / f"{record.capture.sequence:019d}.json"
        )
        self._publish(path, record, "normalization")

    def advance_cursor(self, scope: NormalizationScope, sequence: int) -> NormalizationCursor:
        self._require_lock()
        self._not_blocked()
        cursor = self.cursor(scope)
        if sequence == cursor.through_sequence:
            return cursor
        if sequence != cursor.through_sequence + 1:
            raise CaptureError("normalization_sequence_gap")
        record = self._normalization(scope.digest(), sequence)
        self._validate_normalization(record)
        updated = NormalizationCursor(
            store_id=self.store_id,
            scope=scope,
            through_sequence=sequence,
            record_sha256=record.digest(),
        )
        replace_json(
            self._scope_directory(scope) / "cursor.json",
            updated.document(),
            checkpoint=self.checkpoint,
            stage="cursor",
        )
        return updated

    def confirmation(self, object_id: str) -> UploadConfirmation:
        pending = self.pending(object_id)
        record = self._read(self.root / "confirmations" / (object_id + ".json"), UploadConfirmation)
        self._validate_confirmation(record, pending)
        return record

    def _validate_confirmation(self, record: UploadConfirmation, pending: UploadPending) -> None:
        if (
            record.store_id != self.store_id
            or record.object_id != pending.object_id()
            or record.pending_sha256 != pending.digest()
            or (record.size, record.crc32c, record.md5_hash)
            != (pending.size, pending.crc32c, pending.md5_hash)
        ):
            raise CaptureError("upload_confirmation_mismatch")
        for reference in pending.captures:
            if record.confirmed_at < self._check_reference(reference).completed_at:
                raise CaptureError("upload_confirmation_time_invalid")

    def publish_confirmation(self, record: UploadConfirmation) -> None:
        self._validate_confirmation(record, self.pending(record.object_id))
        self._publish(
            self.root / "confirmations" / (record.object_id + ".json"), record, "confirmation"
        )

    def expiry(
        self, intent: Intent, receipt: Receipt
    ) -> tuple[ExpiryIntent, ExpiryCompletion | None]:
        # Read-only: no API in this slice can publish an expiry intent or remove raw.
        path = self.root / "expiry" / (str(intent.capture_id) + ".intent.json")
        record = self._read(path, ExpiryIntent)
        self._check_reference(record.capture)
        if (
            record.capture.capture_id != intent.capture_id
            or record.payload_sha256 != receipt.sha256
            or record.payload_bytes != receipt.byte_length
        ):
            raise CaptureError("expiry_capture_mismatch")
        policy = self._read(
            self.root / "policies" / (record.policy_sha256 + ".json"), RetentionPolicy
        )
        if (
            policy.digest() != record.policy_sha256
            or policy.normalization_scope_id != record.scope_id
            or policy.accepted_at > record.recorded_at
            or record.eligible_at != receipt.received_at + timedelta(seconds=policy.raw_seconds)
        ):
            raise CaptureError("expiry_policy_mismatch")
        normalized = self._normalization(record.scope_id, record.capture.sequence)
        self._validate_normalization(normalized)
        if (
            normalized.capture != record.capture
            or normalized.digest() != record.normalization_sha256
            or normalized.outcome != "complete"
            or normalized.unresolved_count
            or normalized.completed_at > record.recorded_at
            or set(normalized.object_ids) != set(record.confirmation_hashes)
        ):
            raise CaptureError("expiry_normalization_mismatch")
        for object_id, checksum in record.confirmation_hashes.items():
            confirmed = self.confirmation(object_id)
            if confirmed.digest() != checksum or confirmed.confirmed_at > record.recorded_at:
                raise CaptureError("expiry_confirmation_mismatch")
        completion_path = self.root / "expiry" / (str(intent.capture_id) + ".complete.json")
        completion = None
        if completion_path.exists() or completion_path.is_symlink():
            completion = self._read(completion_path, ExpiryCompletion)
            if (
                completion.store_id != self.store_id
                or completion.capture_id != intent.capture_id
                or completion.intent_sha256 != record.digest()
                or completion.completed_at < record.recorded_at
            ):
                raise CaptureError("expiry_completion_mismatch")
        return record, completion

    def _receipt(self, directory: Path, intent: Intent) -> Receipt:
        response = directory / "response"
        payload = response / "payload.bin"
        if response.is_symlink() or payload.is_symlink():
            raise CaptureError("integrity_failure")
        expiry_path = self.root / "expiry" / (str(intent.capture_id) + ".intent.json")
        receipt = (
            super()._receipt(directory, intent)
            if payload.exists()
            else Receipt.model_validate(read_json(response / "receipt.json"))
        )
        if not payload.exists() or expiry_path.exists() or expiry_path.is_symlink():
            _, completed = self.expiry(intent, receipt)
            if payload.exists() and completed is not None:
                raise CaptureError("expiry_payload_still_present")
        return receipt

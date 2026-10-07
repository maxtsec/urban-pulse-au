"""Full v3 verification, including downstream references and intentional expiry."""

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

from urbanpulse.adapters.capture_checkpoint import CheckpointJournal
from urbanpulse.adapters.capture_journal import read_json
from urbanpulse.adapters.capture_v3 import V3Journal
from urbanpulse.adapters.capture_verify import CaptureVerifier, VerificationInterrupted
from urbanpulse.contracts.capture_delivery import NormalizationCursor, RetentionPolicy
from urbanpulse.contracts.local_capture import CaptureError, Intent, Receipt


class V3Verifier(CaptureVerifier, V3Journal):
    def _open_store(self, initialize: bool) -> None:
        self.legacy = False
        CheckpointJournal._open_store(self, False)

    def _entries(self, directory: Path, stopped: Callable[[], bool]) -> Iterator[Path]:
        for entry in directory.iterdir():
            if stopped():
                raise VerificationInterrupted("verification_interrupted")
            if entry.is_symlink():
                raise CaptureError("delivery_record_invalid")
            if entry.name.startswith((".pending-", ".control-")):
                continue
            yield entry

    def _scan(self, stopped: Callable[[], bool]) -> dict[str, Any]:
        report = super()._scan(stopped)
        normalized_count = uploaded_count = confirmed_count = 0
        for path in self._entries(self.root / "normalization", stopped):
            if not path.is_dir():
                raise CaptureError("normalization_identity_mismatch")
            document = read_json(path / "cursor.json")
            document.pop("checksum", None)
            raw_cursor = NormalizationCursor.model_validate(document)
            if path.name != raw_cursor.scope.digest():
                raise CaptureError("normalization_identity_mismatch")
            cursor = self.cursor(raw_cursor.scope)
            if {p.name for p in self._entries(path, stopped)} != {"cursor.json", "records"}:
                raise CaptureError("delivery_record_invalid")
            sequences: set[int] = set()
            for entry in self._entries(path / "records", stopped):
                sequence = int(entry.stem)
                if entry.name != f"{sequence:019d}.json":
                    raise CaptureError("normalization_identity_mismatch")
                record = self._normalization(path.name, sequence)
                self._validate_normalization(record)
                if sequence < 1 or sequence > cursor.through_sequence + 1:
                    raise CaptureError("normalization_sequence_gap")
                sequences.add(sequence)
                normalized_count += 1
            committed = {s for s in sequences if s <= cursor.through_sequence}
            if len(committed) != cursor.through_sequence:
                raise CaptureError("normalization_sequence_gap")
        unconfirmed_captures: set[UUID] = set()
        for path in self._entries(self.root / "uploads", stopped):
            pending = self.pending(path.stem)
            if path.name != pending.object_id() + ".json":
                raise CaptureError("upload_identity_mismatch")
            if not (self.root / "confirmations" / (pending.object_id() + ".json")).exists():
                unconfirmed_captures.update(ref.capture_id for ref in pending.captures)
            uploaded_count += 1
        for path in self._entries(self.root / "confirmations", stopped):
            confirmed = self.confirmation(path.stem)
            if path.name != confirmed.object_id + ".json":
                raise CaptureError("upload_identity_mismatch")
            confirmed_count += 1
        for path in self._entries(self.root / "policies", stopped):
            policy = self._read(path, RetentionPolicy)
            if path.name != policy.digest() + ".json":
                raise CaptureError("expiry_policy_mismatch")
        expired_bytes = expired_count = expiry_pending = 0
        for path in self._entries(self.root / "expiry", stopped):
            suffix = ".intent.json" if path.name.endswith(".intent.json") else ".complete.json"
            identity = UUID(path.name.removesuffix(suffix))
            if path.name != str(identity) + suffix:
                raise CaptureError("expiry_identity_mismatch")
            directory = self._capture(identity)
            intent = Intent.model_validate(read_json(directory / "intent.json"))
            receipt = Receipt.model_validate(read_json(directory / "response" / "receipt.json"))
            _, completion = self.expiry(intent, receipt)
            if identity in unconfirmed_captures:
                raise CaptureError("expiry_has_unconfirmed_upload")
            if suffix == ".intent.json":
                missing = not (directory / "response" / "payload.bin").exists()
                expired_count += int(missing)
                expired_bytes += receipt.byte_length if missing else 0
                expiry_pending += int(completion is None)
        report.update(
            integrity_scope="retained-payload-hashes-and-expired-provenance",
            normalization_records=normalized_count,
            upload_records=uploaded_count,
            confirmation_records=confirmed_count,
            expired_captures=expired_count,
            expired_payload_bytes=expired_bytes,
            retained_payload_bytes=report["payload_bytes"] - expired_bytes,
            expiry_pending=expiry_pending,
            recovery_required=bool(expiry_pending),
        )
        if expiry_pending:
            report["status"] = "incomplete"
        return report

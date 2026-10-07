"""Bounded v3 downstream records; no default retention or deletion authorization."""

import base64
import hashlib
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from urbanpulse.contracts.capture_control import MAX_SEQUENCE, canonical

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Sequence = Annotated[int, Field(strict=True, ge=1, lt=MAX_SEQUENCE)]
Token = Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,99}$")]


class DeliveryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def digest(self) -> str:
        return hashlib.sha256(canonical(self.model_dump(mode="json"))).hexdigest()


class CaptureReference(DeliveryRecord):
    store_id: UUID
    capture_id: UUID
    sequence: Sequence
    # Hash of the complete canonical receipt; None only for unsuccessful captures.
    receipt_sha256: Digest | None


class NormalizationScope(DeliveryRecord):
    normalizer_revision: Token
    area_revision: Digest
    static_revision: Digest


class NormalizationRecord(DeliveryRecord):
    schema_version: Literal["capture-normalization-v1"] = "capture-normalization-v1"
    capture: CaptureReference
    scope: NormalizationScope
    outcome: Literal["complete", "quarantined"]
    unresolved_count: int = Field(default=0, ge=0, strict=True)
    object_ids: tuple[Digest, ...] = Field(default=(), max_length=32)
    completed_at: AwareDatetime

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if len(set(self.object_ids)) != len(self.object_ids):
            raise ValueError("duplicate_upload_reference")
        if self.outcome == "complete" and self.unresolved_count:
            raise ValueError("complete_with_unresolved_records")
        if self.outcome == "complete" and not self.object_ids:
            raise ValueError("complete_requires_export_manifest")
        return self


class ObjectChecksums(DeliveryRecord):
    size: int = Field(ge=0, le=8 * 1024 * 1024, strict=True)
    crc32c: str = Field(max_length=8)
    md5_hash: str = Field(max_length=24)

    @model_validator(mode="after")
    def checksum_lengths(self) -> Self:
        for value, length in ((self.crc32c, 4), (self.md5_hash, 16)):
            decoded = base64.b64decode(value, validate=True)
            if len(decoded) != length or base64.b64encode(decoded).decode() != value:
                raise ValueError("invalid_checksum_encoding")
        return self


class UploadPending(ObjectChecksums):
    schema_version: Literal["capture-upload-pending-v1"] = "capture-upload-pending-v1"
    store_id: UUID
    bucket: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,220}[a-z0-9]$")
    name: str = Field(min_length=1, max_length=1024)
    sha256: Digest
    captures: tuple[CaptureReference, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def identity(self) -> Self:
        if any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in self.name):
            raise ValueError("invalid_object_name")
        if len(self.name.encode("utf-8")) > 1024:
            raise ValueError("invalid_object_name")
        if any(ref.store_id != self.store_id for ref in self.captures):
            raise ValueError("foreign_capture")
        if len({ref.sequence for ref in self.captures}) != len(self.captures):
            raise ValueError("duplicate_capture")
        return self

    def object_id(self) -> str:
        return hashlib.sha256(canonical([self.bucket, self.name])).hexdigest()


class UploadConfirmation(ObjectChecksums):
    schema_version: Literal["capture-upload-confirmation-v1"] = "capture-upload-confirmation-v1"
    store_id: UUID
    object_id: Digest
    pending_sha256: Digest
    generation: str = Field(pattern=r"^[1-9][0-9]{0,19}$")
    confirmed_at: AwareDatetime


class NormalizationCursor(DeliveryRecord):
    schema_version: Literal["capture-normalization-cursor-v1"] = "capture-normalization-cursor-v1"
    store_id: UUID
    scope: NormalizationScope
    through_sequence: int = Field(default=0, strict=True, ge=0, lt=MAX_SEQUENCE)
    record_sha256: Digest | None = None

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if (self.through_sequence == 0) != (self.record_sha256 is None):
            raise ValueError("cursor_reference_required")
        return self

    def document(self) -> dict[str, object]:
        return {**self.model_dump(mode="json"), "checksum": self.digest()}


class RetentionPolicy(DeliveryRecord):
    schema_version: Literal["capture-retention-policy-v1"] = "capture-retention-policy-v1"
    policy_version: Token
    normalization_scope_id: Digest
    raw_seconds: int = Field(strict=True, gt=0, le=10 * 366 * 86400)
    accepted_at: AwareDatetime
    decision_reference: Token


class ExpiryIntent(DeliveryRecord):
    schema_version: Literal["capture-expiry-intent-v1"] = "capture-expiry-intent-v1"
    capture: CaptureReference
    policy_sha256: Digest
    scope_id: Digest
    normalization_sha256: Digest
    confirmation_hashes: dict[Digest, Digest] = Field(min_length=1, max_length=32)
    payload_sha256: Digest
    payload_bytes: int = Field(strict=True, ge=0, le=8 * 1024 * 1024)
    eligible_at: AwareDatetime
    recorded_at: AwareDatetime

    @model_validator(mode="after")
    def eligible(self) -> Self:
        if self.capture.receipt_sha256 is None or self.recorded_at < self.eligible_at:
            raise ValueError("invalid_expiry_eligibility")
        return self


class ExpiryCompletion(DeliveryRecord):
    schema_version: Literal["capture-expiry-completion-v1"] = "capture-expiry-completion-v1"
    store_id: UUID
    capture_id: UUID
    intent_sha256: Digest
    completed_at: AwareDatetime

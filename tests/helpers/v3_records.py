"""Synthetic ledger data only; no provider payloads or cloud confirmation claim."""

import base64
import hashlib
from datetime import timedelta

from urbanpulse.contracts.capture_delivery import (
    NormalizationRecord,
    NormalizationScope,
    UploadConfirmation,
    UploadPending,
)


def records(journal, sequence=1):
    reference, manifest = journal.reference(sequence)
    payload = b"123456789"
    scope = NormalizationScope(
        normalizer_revision="synthetic-v1", area_revision="a" * 64, static_revision="b" * 64
    )
    pending = UploadPending(
        store_id=journal.store_id,
        bucket="synthetic-landing",
        name=f"synthetic/{reference.capture_id}/records.json",
        sha256=hashlib.sha256(payload).hexdigest(),
        size=len(payload),
        crc32c=base64.b64encode(bytes.fromhex("e3069283")).decode(),
        md5_hash=base64.b64encode(hashlib.md5(payload, usedforsecurity=False).digest()).decode(),
        captures=(reference,),
    )
    normalization = NormalizationRecord(
        capture=reference,
        scope=scope,
        outcome="complete",
        object_ids=(pending.object_id(),),
        completed_at=manifest.completed_at + timedelta(seconds=1),
    )
    confirmation = UploadConfirmation(
        store_id=journal.store_id,
        object_id=pending.object_id(),
        pending_sha256=pending.digest(),
        generation="12345",
        size=pending.size,
        crc32c=pending.crc32c,
        md5_hash=pending.md5_hash,
        confirmed_at=normalization.completed_at + timedelta(seconds=1),
    )
    return scope, pending, normalization, confirmation


def deliver(journal, sequence=1):
    scope, pending, normalized, confirmed = records(journal, sequence)
    journal.initialize_scope(scope)
    journal.publish_pending(pending)
    journal.publish_normalization(normalized)
    journal.advance_cursor(scope, sequence)
    journal.publish_confirmation(confirmed)
    return scope, pending, normalized, confirmed

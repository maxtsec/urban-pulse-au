"""Cross-platform validation of the bounded v3 downstream wire records."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from urbanpulse.contracts.capture_delivery import (
    CaptureReference,
    NormalizationCursor,
    NormalizationRecord,
    NormalizationScope,
    ObjectChecksums,
    RetentionPolicy,
    UploadPending,
)


@pytest.mark.parametrize(
    "crc,md5",
    [
        ("", ""),
        ("AAAAAA==", "AAAA"),
        ("AAAAAB==", "AAAAAAAAAAAAAAAAAAAAAA=="),
        ("AAAAAA==", "AAAAAAAAAAAAAAAAAAAAAB=="),
        ("not-base64", "x"),
    ],
)
def test_invalid_or_noncanonical_checksums_fail(crc, md5):
    with pytest.raises(ValidationError):
        ObjectChecksums(size=1, crc32c=crc, md5_hash=md5)


def test_retention_has_no_implicit_duration_or_scope():
    with pytest.raises(ValidationError):
        RetentionPolicy(
            policy_version="test", accepted_at=datetime.now(UTC), decision_reference="test"
        )


def test_cursor_requires_exact_commit_reference():
    scope = NormalizationScope(
        normalizer_revision="test", area_revision="a" * 64, static_revision="b" * 64
    )
    base = dict(store_id=uuid4(), scope=scope)
    assert NormalizationCursor(**base).through_sequence == 0
    for fields in [
        dict(through_sequence=1),
        dict(record_sha256="c" * 64),
        dict(through_sequence=True),
    ]:
        with pytest.raises(ValidationError):
            NormalizationCursor(**base, **fields)


@pytest.mark.parametrize(
    "change", [{"unresolved_count": 1}, {"object_ids": ()}, {"object_ids": ("c" * 64, "c" * 64)}]
)
def test_complete_normalization_requires_unique_exports_and_no_unresolved(change):
    ref = CaptureReference(
        store_id=uuid4(), capture_id=uuid4(), sequence=1, receipt_sha256="d" * 64
    )
    fields = dict(
        capture=ref,
        scope=NormalizationScope(
            normalizer_revision="test", area_revision="a" * 64, static_revision="b" * 64
        ),
        outcome="complete",
        object_ids=("c" * 64,),
        completed_at=datetime.now(UTC),
    )
    fields.update(change)
    with pytest.raises(ValidationError):
        NormalizationRecord(**fields)


@pytest.mark.parametrize("name", ["bad\x00name", "bad\ud800name", "電" * 400])
def test_upload_name_must_be_bounded_serializable_utf8(name):
    store = uuid4()
    ref = CaptureReference(store_id=store, capture_id=uuid4(), sequence=1, receipt_sha256=None)
    with pytest.raises(ValidationError):
        UploadPending(
            store_id=store,
            bucket="synthetic-bucket",
            name=name,
            captures=(ref,),
            size=0,
            crc32c="AAAAAA==",
            md5_hash="AAAAAAAAAAAAAAAAAAAAAA==",
            sha256="a" * 64,
        )


def test_failed_capture_cannot_be_marked_complete_without_exporting_coverage():
    reference = CaptureReference(
        store_id=uuid4(), capture_id=uuid4(), sequence=1, receipt_sha256=None
    )
    with pytest.raises(ValidationError, match="export_manifest"):
        NormalizationRecord(
            capture=reference,
            scope=NormalizationScope(
                normalizer_revision="test", area_revision="a" * 64, static_revision="b" * 64
            ),
            outcome="complete",
            object_ids=(),
            completed_at=datetime.now(UTC),
        )


@pytest.mark.parametrize("version_args", [[], ["--store-version", "v2"]])
def test_live_v2_is_rejected_before_store_or_key_access(tmp_path, version_args):
    import subprocess
    import sys

    store = tmp_path / "must-not-be-created"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "workers.capture.main",
            "run",
            "--live",
            "--store",
            str(store),
            "--key-file",
            str(tmp_path / "missing-key"),
            *version_args,
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2
    assert "live_requires_v3" in result.stderr
    assert not store.exists()

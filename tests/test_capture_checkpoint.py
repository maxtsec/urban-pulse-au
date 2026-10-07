"""V2 filesystem behavior, restart read bounds, verification and legacy isolation."""

import errno
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from urbanpulse.adapters import capture_journal as storage
from urbanpulse.adapters.capture_checkpoint import CheckpointJournal
from urbanpulse.adapters.capture_journal import CaptureJournal
from urbanpulse.adapters.capture_verify import CaptureVerifier
from urbanpulse.adapters.synthetic_capture import SyntheticCapture
from urbanpulse.contracts.local_capture import CaptureError, FetchResult

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux fsync/flock contract")
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def filesystem(monkeypatch):
    monkeypatch.setattr(storage, "local_filesystem", lambda _: "test-filesystem")


@pytest.fixture
def store(tmp_path):
    with CheckpointJournal(tmp_path).locked(initialize=True):
        pass
    return tmp_path


def capture(journal):
    intent = journal.begin("fixture", "vehicle-positions", "test")
    result = SyntheticCapture().fetch("vehicle-positions")
    return intent, result, journal.complete(intent, result)


def crash(store, action, point):
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tests/helpers/checkpoint_process.py"),
            str(store),
            action,
            point,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 77, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("point", "outcome", "reason"),
    [
        ("reserve_written", None, None),
        ("reserve_replaced", "abandoned", "not_started"),
        ("reserve_synced", "abandoned", "not_started"),
        ("intent_written", "abandoned", "not_started"),
        ("intent_replaced", "abandoned", "interrupted"),
        ("intent", "abandoned", "interrupted"),
        ("sequence_written", "abandoned", "interrupted"),
        ("sequence_linked", "abandoned", "interrupted"),
        ("sequence_synced", "abandoned", "interrupted"),
        ("payload", "abandoned", "interrupted"),
        ("receipt", "abandoned", "interrupted"),
        ("response", "captured", None),
        ("manifest", "captured", None),
        ("finalize_written", "captured", None),
        ("finalize_replaced", "captured", None),
        ("finalize_synced", "captured", None),
    ],
)
def test_restart_accounts_once_and_never_reuses_reserved_sequence(store, point, outcome, reason):
    crash(store, "capture", point)
    for _ in range(2):
        with CheckpointJournal(store).locked() as journal:
            summary = journal.recover()
            assert sum(summary["outcomes"].values()) == int(outcome is not None)
            assert summary["next_capture_sequence"] == (2 if outcome else 1)
            if outcome:
                assert summary["outcomes"][outcome] == 1
                manifest = json.loads(
                    next((store / "captures").glob("*/manifest.json")).read_bytes()
                )
                assert manifest["reason"] == reason
    with CheckpointJournal(store).locked() as journal:
        intent, _, _ = capture(journal)
        assert intent.capture_sequence == (2 if outcome else 1)
    with CaptureVerifier(store).locked() as verifier:
        assert verifier.verify()["status"] == "verified"


@pytest.mark.parametrize(
    "point", ["reconstruct_written", "reconstruct_replaced", "reconstruct_synced"]
)
def test_not_started_survives_death_during_reconstruction(store, point):
    crash(store, "capture", "reserve_synced")
    crash(store, "recover", point)
    with CheckpointJournal(store).locked() as journal:
        assert journal.recover()["outcomes"]["abandoned"] == 1
    manifest = json.loads(next((store / "captures").glob("*/manifest.json")).read_bytes())
    assert manifest["reason"] == "not_started"


def test_idle_restart_does_not_open_or_enumerate_history(store, monkeypatch):
    with CheckpointJournal(store).locked() as journal:
        for _ in range(8):
            capture(journal)
    original_read = Path.open
    original_iter = Path.iterdir

    def guard_open(path, *args, **kwargs):
        if "captures" in path.parts or "sessions" in path.parts:
            pytest.fail("historical record opened")
        return original_read(path, *args, **kwargs)

    def guard_iter(path):
        pytest.fail("ordinary startup enumerated a directory")
        return original_iter(path)

    monkeypatch.setattr(Path, "open", guard_open)
    monkeypatch.setattr(Path, "iterdir", guard_iter)
    with CheckpointJournal(store).locked() as journal:
        summary = journal.recover()
        assert summary["outcomes"]["captured"] == 8
        assert summary["orphan_directories"] is None
        assert summary["integrity_scope"] == "checkpoint-and-pending"


def test_pending_restart_reads_only_pending_payload(store, monkeypatch):
    with CheckpointJournal(store).locked() as journal:
        first, _, _ = capture(journal)
    crash(store, "capture", "manifest")
    original = Path.open

    def guard(path, *args, **kwargs):
        assert str(first.capture_id) not in path.parts
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guard)
    with CheckpointJournal(store).locked() as journal:
        assert journal.recover()["outcomes"]["captured"] == 2


def test_completed_retry_and_live_retry_after(store):
    with CheckpointJournal(store).locked() as journal:
        intent, result, manifest = capture(journal)
        assert journal.complete(intent, result) == manifest
        assert journal.recover()["outcomes"]["captured"] == 1
        attempt = journal.begin("live", "service-alerts", "test")
        now = datetime.now(UTC)
        journal.complete(attempt, FetchResult(now, now, 429, None, "http_error", 900))
    with CheckpointJournal(store).locked() as journal:
        status = journal.recover()
        assert status["next_capture_sequence"] == 3
        assert datetime.fromisoformat(status["retry_not_before"]) > now
    with CaptureVerifier(store).locked() as verifier:
        assert verifier.verify()["outcomes"]["fetch-failed"] == 1


@pytest.mark.parametrize("change", ["missing", "checksum", "wrong_store"])
def test_control_is_authoritative_and_never_rebuilt(store, change):
    control = store / "control.json"
    if change == "missing":
        control.unlink()
    elif change == "checksum":
        control.write_text("{}")
    else:
        marker = json.loads((store / "store.json").read_bytes())
        marker["store_id"] = "00000000-0000-0000-0000-000000000000"
        (store / "store.json").write_text(json.dumps(marker))
    with pytest.raises(CaptureError, match="control_invalid"):
        with CheckpointJournal(store).locked():
            pass


def test_full_verify_finds_corruption_and_blocks_until_fixed(store):
    with CheckpointJournal(store).locked() as journal:
        capture(journal)
    payload = next(store.glob("captures/*/response/payload.bin"))
    original = payload.read_bytes()
    payload.write_bytes(b"changed")
    with CheckpointJournal(store).locked() as journal:
        assert journal.recover()["collection_allowed"]
    with pytest.raises(CaptureError, match="integrity_failure"):
        with CaptureVerifier(store).locked() as verifier:
            verifier.verify()
    with CheckpointJournal(store).locked() as journal:
        assert not journal.recover()["collection_allowed"]
        with pytest.raises(CaptureError, match="verification_required"):
            capture(journal)
    # Simulate operator restoring the exact original bytes from a backup.
    payload.write_bytes(original)
    with CaptureVerifier(store).locked() as verifier:
        assert verifier.verify()["status"] == "verified"
    with CheckpointJournal(store).locked() as journal:
        assert journal.recover()["collection_allowed"]


@pytest.mark.parametrize("point", ["verify_started", "verify_capture", "verify_report"])
def test_interrupted_inspection_requires_successful_verify_before_capture(store, point):
    with CheckpointJournal(store).locked() as journal:
        capture(journal)
    crash(store, "verify", point)
    with CheckpointJournal(store).locked() as journal:
        status = journal.recover()
        assert not status["collection_allowed"]
        assert status["verification"] == "interrupted"
        with pytest.raises(CaptureError, match="verification_required"):
            capture(journal)
    with CaptureVerifier(store).locked() as verifier:
        assert verifier.verify()["captures"] == 1
    with CheckpointJournal(store).locked() as journal:
        assert journal.recover()["collection_allowed"]
        capture(journal)


def test_crash_after_finding_preserves_block(store):
    with CheckpointJournal(store).locked() as journal:
        capture(journal)
    next(store.glob("captures/*/response/payload.bin")).write_bytes(b"bad")
    crash(store, "verify", "verify_failed")
    with CheckpointJournal(store).locked() as journal:
        assert journal.recover()["verification"] == "failed"
    crash(store, "verify", "verify_started")
    with CheckpointJournal(store).locked() as journal:
        assert not journal.recover()["collection_allowed"]


def test_verify_does_not_reconcile_pending_or_invent_outcomes(store):
    crash(store, "capture", "reserve_synced")
    before = (store / "control.json").read_bytes()
    with CaptureVerifier(store).locked() as verifier:
        report = verifier.verify()
        assert report["incomplete"] == 1
    assert (store / "control.json").read_bytes() == before
    assert not list((store / "captures").iterdir())


def test_old_valid_control_and_duplicate_sequences_are_detected(store):
    old = (store / "control.json").read_bytes()
    with CheckpointJournal(store).locked() as journal:
        capture(journal)
    (store / "control.json").write_bytes(old)
    with CheckpointJournal(store).locked() as journal:
        assert journal.recover()["outcomes"]["captured"] == 0
    with pytest.raises(CaptureError, match="integrity_failure"):
        with CaptureVerifier(store).locked() as verifier:
            verifier.verify()


def test_legacy_verify_preserves_bytes_and_neither_version_reads_the_other(tmp_path, store):
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    with CaptureJournal(legacy).locked(initialize=True) as journal:
        capture(journal)
        journal.begin("fixture", "service-alerts", "test")
    before = {p.relative_to(legacy): p.read_bytes() for p in legacy.rglob("*") if p.is_file()}
    with CaptureVerifier(legacy).locked() as verifier:
        assert verifier.verify()["incomplete"] == 1
    after = {p.relative_to(legacy): p.read_bytes() for p in legacy.rglob("*") if p.is_file()}
    assert before == after
    with pytest.raises(CaptureError, match="store_version_requires_fresh_v2"):
        with CheckpointJournal(legacy).locked():
            pass
    with pytest.raises(CaptureError, match="store_marker_invalid"):
        with CaptureJournal(store).locked():
            pass


@pytest.mark.parametrize(
    "point", ["initialize_written", "initialize_replaced", "initialize_synced"]
)
def test_partial_initialization_cannot_be_reinterpreted_as_empty(tmp_path, point):
    crash(tmp_path, "init", point)
    with pytest.raises(CaptureError, match="store_not_empty"):
        with CheckpointJournal(tmp_path).locked(initialize=True):
            pass


@pytest.mark.parametrize(
    "point",
    [
        "verify_report",
        "verify_removed_verification-in-progress.json",
        "verify_removed_verification-block.json",
    ],
)
def test_success_cleanup_crash_keeps_failure_block_until_removed(store, point):
    with CheckpointJournal(store).locked() as journal:
        capture(journal)
    payload = next(store.glob("captures/*/response/payload.bin"))
    original = payload.read_bytes()
    payload.write_bytes(b"bad")
    with pytest.raises(CaptureError):
        with CaptureVerifier(store).locked() as verifier:
            verifier.verify()
    payload.write_bytes(original)
    crash(store, "verify", point)
    with CheckpointJournal(store).locked() as journal:
        assert journal.recover()["collection_allowed"] == (
            point == "verify_removed_verification-block.json"
        )
    with CaptureVerifier(store).locked() as verifier:
        assert verifier.verify()["status"] == "verified"


def test_verification_cancel_records_interruption_not_failure(store):
    with CaptureVerifier(store).locked() as verifier:
        with pytest.raises(CaptureError, match="verification_interrupted"):
            verifier.verify(stopped=lambda: True)
    with CheckpointJournal(store).locked() as journal:
        summary = journal.recover()
        assert summary["verification"] == "not_checked"
        assert summary["collection_allowed"]


@pytest.mark.parametrize("storage_errno", [errno.ENOSPC, errno.EROFS])
def test_failure_marker_write_failure_never_claims_success(store, monkeypatch, storage_errno):
    from urbanpulse.adapters import capture_verify

    with CheckpointJournal(store).locked() as journal:
        capture(journal)
    next(store.glob("captures/*/response/payload.bin")).write_bytes(b"bad")
    original = capture_verify.replace_json

    def fail(path, value, **kwargs):
        if path.name == "verification-block.json":
            raise OSError(storage_errno, "storage unavailable")
        original(path, value, **kwargs)

    monkeypatch.setattr(capture_verify, "replace_json", fail)
    with pytest.raises(CaptureError, match="verification_failure_record_unwritable"):
        with CaptureVerifier(store).locked() as verifier:
            verifier.verify()
    assert not (store / "last-verification.json").exists()
    with CheckpointJournal(store).locked() as journal:
        assert not journal.recover()["collection_allowed"]
        with pytest.raises(CaptureError, match="verification_required"):
            capture(journal)


def test_duplicate_archive_sequence_is_detected(store):
    with CheckpointJournal(store).locked() as journal:
        capture(journal)
        second, _, _ = capture(journal)
    path = store / "captures" / str(second.capture_id) / "intent.json"
    value = json.loads(path.read_bytes())
    value["capture_sequence"] = 1
    path.write_text(json.dumps(value))
    with pytest.raises(CaptureError, match="integrity_failure"):
        with CaptureVerifier(store).locked() as verifier:
            verifier.verify()


def test_sequence_exhaustion_stops_before_publication(store):
    from urbanpulse.adapters.capture_checkpoint import replace_json
    from urbanpulse.contracts.capture_control import MAX_SEQUENCE, Control, Summary

    with CheckpointJournal(store).locked() as journal:
        control = Control(
            store_id=journal.control.store_id,
            generation=2 * (MAX_SEQUENCE - 1),
            next_capture_sequence=MAX_SEQUENCE,
            summary=Summary(
                outcomes={
                    "captured": MAX_SEQUENCE - 1,
                    "fetch-failed": 0,
                    "raw-write-failed": 0,
                    "abandoned": 0,
                }
            ),
        )
        replace_json(store / "control.json", control.document())
    with CheckpointJournal(store).locked() as journal:
        with pytest.raises(CaptureError, match="capture_sequence_exhausted"):
            capture(journal)
    assert not list((store / "captures").iterdir())


def test_v2_cli_verify_is_offline_and_has_full_integrity_scope(store):
    command = [sys.executable, str(ROOT / "tests/helpers/capture_process.py"), str(store), "cli"]
    with CheckpointJournal(store).locked() as journal:
        capture(journal)
    result = subprocess.run(
        [*command, "verify", "--store", str(store)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "verified"
    assert report["integrity_scope"] == "full-published-capture-history"
    with CheckpointJournal(store).locked() as journal:
        assert journal.recover()["last_verification"]["generation"] == 2


@pytest.mark.parametrize(
    "point", ["verify_progress_written", "verify_progress_replaced", "verify_progress_synced"]
)
def test_verify_start_publication_holds_before_any_archive_read(store, point):
    crash(store, "verify", point)
    with CheckpointJournal(store).locked() as journal:
        # Before publishing the hold, the verifier has not read any archive data.
        assert journal.recover()["collection_allowed"] == (point == "verify_progress_written")


@pytest.mark.parametrize(
    "point", ["verify_failure_written", "verify_failure_replaced", "verify_failure_synced"]
)
def test_finding_block_publication_boundaries(store, point):
    with CheckpointJournal(store).locked() as journal:
        capture(journal)
    next(store.glob("captures/*/response/payload.bin")).write_bytes(b"bad")
    crash(store, "verify", point)
    with CheckpointJournal(store).locked() as journal:
        status = journal.recover()
        # The pre-scan hold covers even a failure record that never publishes.
        assert not status["collection_allowed"]
    with pytest.raises(CaptureError, match="integrity_failure"):
        with CaptureVerifier(store).locked() as verifier:
            verifier.verify()


@pytest.mark.parametrize(
    "point", ["verify_result_written", "verify_result_replaced", "verify_result_synced"]
)
def test_success_report_publication_never_erases_existing_failure_early(store, point):
    with CheckpointJournal(store).locked() as journal:
        capture(journal)
    payload = next(store.glob("captures/*/response/payload.bin"))
    original = payload.read_bytes()
    payload.write_bytes(b"bad")
    with pytest.raises(CaptureError):
        with CaptureVerifier(store).locked() as verifier:
            verifier.verify()
    payload.write_bytes(original)
    crash(store, "verify", point)
    with CheckpointJournal(store).locked() as journal:
        assert not journal.recover()["collection_allowed"]


@pytest.mark.parametrize("state", ["reserved", "intent", "fetch-failed", "raw-write-failed"])
def test_clock_rollback_cannot_publish_unverifiable_terminal_time(store, monkeypatch, state):
    from urbanpulse.adapters import capture_checkpoint

    requested = datetime.now(UTC) + timedelta(seconds=30)

    class FutureClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return requested

    if state == "reserved":

        def die(stage):
            if stage == "reserve_synced":
                raise RuntimeError("simulated crash")

        with monkeypatch.context() as patch:
            patch.setattr(capture_checkpoint, "datetime", FutureClock)
            with pytest.raises(RuntimeError):
                with CheckpointJournal(store, checkpoint=die).locked() as journal:
                    journal.begin("fixture", "vehicle-positions", "test")
    else:
        with CheckpointJournal(store).locked() as journal:
            with monkeypatch.context() as patch:
                patch.setattr(capture_checkpoint, "datetime", FutureClock)
                intent = journal.begin("live", "vehicle-positions", "test")
            now = datetime.now(UTC)
            if state == "fetch-failed":
                result = FetchResult(now, now, 429, None, "http_error", 900)
                manifest = journal.complete(intent, result)
                assert journal.complete(intent, result) == manifest
                assert manifest.retry_not_before >= requested + timedelta(seconds=900)
            elif state == "raw-write-failed":
                original = storage.write_bytes

                def fail(path, data):
                    if path.name == "payload.bin":
                        raise OSError("full")
                    original(path, data)

                with monkeypatch.context() as patch:
                    patch.setattr(storage, "write_bytes", fail)
                    with pytest.raises(CaptureError, match="storage_error"):
                        journal.complete(
                            intent, FetchResult(requested, requested, 200, b"synthetic")
                        )
    with CheckpointJournal(store).locked() as journal:
        assert sum(journal.recover()["outcomes"].values()) == 1
        assert journal.capture_at_sequence(1).requested_at == requested
    manifest = json.loads(next(store.glob("captures/*/manifest.json")).read_bytes())
    assert datetime.fromisoformat(manifest["completed_at"]) == requested
    for _ in range(2):
        with CaptureVerifier(store).locked() as verifier:
            assert verifier.verify()["status"] == "verified"
    with CheckpointJournal(store).locked() as journal:
        assert journal.recover()["collection_allowed"]


def test_sequence_lookup_opens_only_named_index_and_intent(store, monkeypatch):
    with CheckpointJournal(store).locked() as journal:
        intents = [capture(journal)[0] for _ in range(5)]
    original = Path.open
    opened = []

    def record(path, *args, **kwargs):
        opened.append(path)
        return original(path, *args, **kwargs)

    def no_scan(path):
        pytest.fail("cursor lookup scanned a directory")

    with CheckpointJournal(store).locked() as journal:
        monkeypatch.setattr(Path, "open", record)
        monkeypatch.setattr(Path, "iterdir", no_scan)
        assert journal.capture_at_sequence(4) == intents[3]
        assert opened == [
            store / "by-sequence" / "0000000000000000004",
            store / "captures" / str(intents[3].capture_id) / "intent.json",
        ]
        assert journal.capture_at_sequence(6) is None


def test_unfinished_sequence_never_advances_downstream_cursor(store):
    with CheckpointJournal(store).locked() as journal:
        intent = journal.begin("fixture", "vehicle-positions", "test")
        assert (store / "by-sequence" / "0000000000000000001").exists()
        assert journal.capture_at_sequence(1) is None
        journal.recover()
        assert journal.capture_at_sequence(1) == intent


@pytest.mark.parametrize("damage", ["missing", "wrong_id", "extra", "symlink"])
def test_verify_detects_invalid_sequence_index(store, damage):
    with CheckpointJournal(store).locked() as journal:
        capture(journal)
    entry = store / "by-sequence" / "0000000000000000001"
    if damage == "missing":
        entry.unlink()
    elif damage == "wrong_id":
        value = json.loads(entry.read_bytes())
        value["capture_id"] = "00000000-0000-0000-0000-000000000000"
        entry.write_text(json.dumps(value))
    elif damage == "extra":
        (entry.parent / "0000000000000000002").write_bytes(entry.read_bytes())
    else:
        entry.unlink()
        entry.symlink_to(store / "control.json")
    with pytest.raises(CaptureError, match="integrity_failure"):
        with CaptureVerifier(store).locked() as verifier:
            verifier.verify()
    with CheckpointJournal(store).locked() as journal:
        assert not journal.recover()["collection_allowed"]


def test_pending_recovery_refuses_conflicting_index(store):
    crash(store, "capture", "sequence_synced")
    entry = store / "by-sequence" / "0000000000000000001"
    entry.write_text("{}")
    with pytest.raises(CaptureError, match="sequence_index_conflict"):
        with CheckpointJournal(store).locked() as journal:
            journal.recover()
    assert entry.read_text() == "{}"


@pytest.mark.parametrize("prior", ["interrupted", "failed"])
def test_cancel_cannot_clear_preexisting_verification_hold(store, prior):
    if prior == "failed":
        with CheckpointJournal(store).locked() as journal:
            capture(journal)
        next(store.glob("captures/*/response/payload.bin")).write_bytes(b"bad")
        with pytest.raises(CaptureError):
            with CaptureVerifier(store).locked() as verifier:
                verifier.verify()
    else:
        crash(store, "verify", "verify_started")
    with CaptureVerifier(store).locked() as verifier:
        with pytest.raises(CaptureError, match="verification_interrupted"):
            verifier.verify(stopped=lambda: True)
    with CheckpointJournal(store).locked() as journal:
        assert not journal.recover()["collection_allowed"]


@pytest.mark.parametrize(
    "failure", [RuntimeError("unexpected private diagnostic"), TypeError("unexpected")]
)
def test_unexpected_verify_errors_fail_closed_and_are_redacted(store, monkeypatch, failure):
    def fail(*_):
        raise failure

    monkeypatch.setattr(CaptureVerifier, "_scan", fail)
    with pytest.raises(CaptureError, match="^integrity_failure$"):
        with CaptureVerifier(store).locked() as verifier:
            verifier.verify()
    with CheckpointJournal(store).locked() as journal:
        assert not journal.recover()["collection_allowed"]


def test_verify_does_not_scan_if_hold_cannot_be_persisted(store, monkeypatch):
    from urbanpulse.adapters import capture_verify

    def fail(*_, **__):
        raise OSError("read only")

    def must_not_scan(*_):
        pytest.fail("archive read before durable hold")

    monkeypatch.setattr(capture_verify, "replace_json", fail)
    monkeypatch.setattr(CaptureVerifier, "_scan", must_not_scan)
    with pytest.raises(OSError):
        with CaptureVerifier(store).locked() as verifier:
            verifier.verify()

"""V3 integrity, ordered progress, version isolation and process-death recovery."""

import json
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest

from urbanpulse.adapters import capture_journal as storage
from urbanpulse.adapters.capture_checkpoint import CheckpointJournal
from urbanpulse.adapters.capture_journal import publish_json
from urbanpulse.adapters.capture_v3 import V3Journal
from urbanpulse.adapters.capture_v3_verify import V3Verifier
from urbanpulse.adapters.capture_verify import CaptureVerifier
from urbanpulse.adapters.synthetic_capture import SyntheticCapture
from urbanpulse.contracts.capture_delivery import ExpiryCompletion, ExpiryIntent, RetentionPolicy
from urbanpulse.contracts.local_capture import CaptureError

sys.path.insert(0, str(Path(__file__).parent / "helpers"))
from v3_records import deliver, records

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux fsync/flock contract")
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def filesystem(monkeypatch):
    monkeypatch.setattr(storage, "local_filesystem", lambda _: "test-filesystem")


@pytest.fixture
def store(tmp_path):
    with V3Journal(tmp_path).locked(initialize=True):
        pass
    return tmp_path


def capture(journal):
    intent = journal.begin("fixture", "vehicle-positions", "synthetic-v3")
    journal.complete(intent, SyntheticCapture().fetch("vehicle-positions"))
    return intent


def crash(store, action, point):
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tests/helpers/delivery_process.py"),
            str(store),
            action,
            point,
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 77, result.stdout + result.stderr


def expired_fixture(journal, *, remove=True, complete=True):
    """Simulate a future expiry writer; production currently has no delete operation."""
    intent = capture(journal)
    _, pending, normalized, confirmed = deliver(journal)
    reference, manifest = journal.reference(1)
    receipt = manifest.receipt
    policy = RetentionPolicy(
        policy_version="synthetic-retention",
        normalization_scope_id=normalized.scope.digest(),
        raw_seconds=60,
        accepted_at=receipt.received_at,
        decision_reference="test-only",
    )
    recorded = receipt.received_at + timedelta(seconds=60)
    expiry = ExpiryIntent(
        capture=reference,
        policy_sha256=policy.digest(),
        scope_id=normalized.scope.digest(),
        normalization_sha256=normalized.digest(),
        confirmation_hashes={pending.object_id(): confirmed.digest()},
        payload_sha256=receipt.sha256,
        payload_bytes=receipt.byte_length,
        eligible_at=recorded,
        recorded_at=recorded,
    )
    publish_json(
        journal.root / "policies" / (policy.digest() + ".json"), policy.model_dump(mode="json")
    )
    path = journal.root / "expiry" / (str(intent.capture_id) + ".intent.json")
    publish_json(path, expiry.model_dump(mode="json"))
    payload = journal.root / "captures" / str(intent.capture_id) / "response" / "payload.bin"
    if remove:
        payload.unlink()
        storage.sync_directory(payload.parent)
    if complete:
        completion = ExpiryCompletion(
            store_id=journal.store_id,
            capture_id=intent.capture_id,
            intent_sha256=expiry.digest(),
            completed_at=recorded,
        )
        publish_json(
            path.with_name(str(intent.capture_id) + ".complete.json"),
            completion.model_dump(mode="json"),
        )
    return path, payload, expiry


def test_fresh_v3_marker_and_v2_refuse_each_other(store, tmp_path):
    assert json.loads((store / "store.json").read_bytes())["schema_version"] == "capture-store-v3"
    for cls in (CheckpointJournal, CaptureVerifier):
        with pytest.raises(CaptureError, match="store_marker_invalid"):
            with cls(store).locked():
                pass
    old = tmp_path / "old"
    old.mkdir()
    with CheckpointJournal(old).locked(initialize=True):
        pass
    with pytest.raises(CaptureError, match="store_marker_invalid"):
        with V3Journal(old).locked():
            pass


@pytest.mark.parametrize(
    "point",
    [
        "reserve_written",
        "reserve_replaced",
        "reserve_synced",
        "intent_written",
        "intent_replaced",
        "intent",
        "sequence_written",
        "sequence_linked",
        "sequence_synced",
        "payload",
        "receipt",
        "response",
        "manifest",
        "finalize_written",
        "finalize_replaced",
        "finalize_synced",
    ],
)
def test_v3_capture_crash_recovery_is_still_bounded_and_counts_once(store, point):
    crash(store, "capture", point)
    for _ in range(2):
        with V3Journal(store).locked() as journal:
            status = journal.recover()
            assert sum(status["outcomes"].values()) == int(point != "reserve_written")
    with V3Verifier(store).locked() as verifier:
        assert verifier.verify()["status"] == "verified"


@pytest.mark.parametrize(
    "point",
    [
        "scope_written",
        "scope_published",
        "scope_synced",
        *[
            f"{step}_{stage}"
            for step in ("upload", "normalization", "confirmation")
            for stage in ("written", "linked", "synced", "cleaned")
        ],
        "cursor_written",
        "cursor_replaced",
        "cursor_synced",
    ],
)
def test_progress_crash_retries_reuse_records_and_preserve_raw(store, point):
    with V3Journal(store).locked() as journal:
        capture(journal)
    original = next(store.glob("captures/*/response/payload.bin")).read_bytes()
    crash(store, "delivery", point)
    for _ in range(2):
        with V3Journal(store).locked() as journal:
            journal.recover()
            scope, pending, normalized, confirmed = deliver(journal)
            assert journal.cursor(scope).through_sequence == 1
            assert journal.confirmation(pending.object_id()) == confirmed
            assert journal.reference(1)[0] == normalized.capture
    assert next(store.glob("captures/*/response/payload.bin")).read_bytes() == original
    with V3Verifier(store).locked() as verifier:
        report = verifier.verify()
        assert report["normalization_records"] == report["upload_records"] == 1
        assert report["confirmation_records"] == 1 and report["expired_captures"] == 0


def test_cursor_cannot_skip_unpublished_capture_or_rewind(store):
    with V3Journal(store).locked() as journal:
        capture(journal)
        capture(journal)
        scope, pending, normalized, _ = records(journal)
        journal.initialize_scope(scope)
        with pytest.raises(CaptureError):
            journal.advance_cursor(scope, 1)
        with pytest.raises(CaptureError):
            journal.publish_normalization(normalized)
        journal.publish_pending(pending)
        with pytest.raises(CaptureError, match="sequence_gap"):
            journal.advance_cursor(scope, 2)
        journal.publish_normalization(normalized)
        journal.advance_cursor(scope, 1)
        with pytest.raises(CaptureError, match="sequence_gap"):
            journal.advance_cursor(scope, 0)
        with pytest.raises(CaptureError, match="not_finalized"):
            journal.reference(3)


def test_progress_conflict_and_foreign_capture_fail_without_overwrite(store):
    with V3Journal(store).locked() as journal:
        capture(journal)
        _, pending, _, confirmed = deliver(journal)
        with pytest.raises(CaptureError, match="conflict"):
            journal.publish_pending(pending.model_copy(update={"sha256": "c" * 64}))
        with pytest.raises(CaptureError, match="mismatch"):
            journal.publish_confirmation(confirmed.model_copy(update={"size": 1}))
        assert journal.pending(pending.object_id()) == pending


def test_verification_hold_blocks_all_progress_writes(store):
    with V3Journal(store).locked() as journal:
        capture(journal)
        scope, pending, normalized, confirmed = deliver(journal)
        publish_json(store / "verification-in-progress.json", {})
        operations = [
            lambda: journal.initialize_scope(scope),
            lambda: journal.publish_pending(pending),
            lambda: journal.publish_normalization(normalized),
            lambda: journal.advance_cursor(scope, 1),
            lambda: journal.publish_confirmation(confirmed),
        ]
        for operation in operations:
            with pytest.raises(CaptureError, match="verification_required"):
                operation()


def test_expired_payload_is_valid_only_with_full_matching_provenance(store):
    with V3Journal(store).locked() as journal:
        path, payload, expiry = expired_fixture(journal)
    with V3Verifier(store).locked() as verifier:
        report = verifier.verify()
        assert report["status"] == "verified" and report["expired_captures"] == 1
        assert report["retained_payload_bytes"] == 0
        assert report["expired_payload_bytes"] == expiry.payload_bytes
        assert report["outcomes"]["captured"] == 1
    with V3Journal(store).locked() as journal:
        assert journal.capture_at_sequence(1).capture_id == expiry.capture.capture_id
        assert journal.recover()["collection_allowed"]
    assert path.exists() and not payload.exists()


@pytest.mark.parametrize("remove", [False, True])
def test_incomplete_expiry_keeps_hold_without_deleting_or_recreating_raw(store, remove):
    with V3Journal(store).locked() as journal:
        _, payload, _ = expired_fixture(journal, remove=remove, complete=False)
    with V3Verifier(store).locked() as verifier:
        report = verifier.verify()
        assert report["status"] == "incomplete" and report["expiry_pending"] == 1
    with V3Journal(store).locked() as journal:
        assert not journal.recover()["collection_allowed"]
    assert payload.exists() == (not remove)


@pytest.mark.parametrize(
    "damage",
    [
        "missing_intent",
        "missing_policy",
        "missing_confirmation",
        "wrong_confirmation",
        "wrong_policy",
        "wrong_size",
        "wrong_scope",
        "payload_present",
        "missing_normalization",
        "wrong_completion",
        "future_normalization",
        "unresolved",
    ],
)
def test_invalid_expiry_is_corruption_and_retains_verification_hold(store, damage):
    with V3Journal(store).locked() as journal:
        path, payload, expiry = expired_fixture(journal, remove=damage != "payload_present")
    if damage == "missing_intent":
        path.unlink()
    elif damage == "missing_policy":
        next((store / "policies").glob("*.json")).unlink()
    elif damage == "missing_confirmation":
        next((store / "confirmations").glob("*.json")).unlink()
    elif damage == "missing_normalization":
        next(store.glob("normalization/*/records/*.json")).unlink()
    elif damage in {"wrong_policy", "wrong_size", "wrong_scope"}:
        value = json.loads(path.read_bytes())
        key = {
            "wrong_policy": "policy_sha256",
            "wrong_size": "payload_bytes",
            "wrong_scope": "scope_id",
        }[damage]
        value[key] = 0 if damage == "wrong_size" else "f" * 64
        path.write_text(json.dumps(value))
    elif damage in {"wrong_confirmation", "wrong_completion", "future_normalization", "unresolved"}:
        pattern = {
            "wrong_confirmation": "confirmations/*.json",
            "wrong_completion": "expiry/*.complete.json",
            "future_normalization": "normalization/*/records/*.json",
            "unresolved": "normalization/*/records/*.json",
        }[damage]
        target = next(store.glob(pattern))
        value = json.loads(target.read_bytes())
        if damage == "wrong_confirmation":
            value["crc32c"] = "AAAAAA=="
        elif damage == "wrong_completion":
            value["intent_sha256"] = "f" * 64
        elif damage == "future_normalization":
            value["completed_at"] = "2099-01-01T00:00:00Z"
        else:
            value["unresolved_count"] = 1
        target.write_text(json.dumps(value))
    with V3Verifier(store).locked() as verifier:
        with pytest.raises(CaptureError):
            verifier.verify()
    with V3Journal(store).locked() as journal:
        assert not journal.recover()["collection_allowed"]


def test_unexplained_missing_payload_blocks_collection(store):
    with V3Journal(store).locked() as journal:
        capture(journal)
    next(store.glob("captures/*/response/payload.bin")).unlink()
    with V3Verifier(store).locked() as verifier:
        with pytest.raises(CaptureError):
            verifier.verify()
    with V3Journal(store).locked() as journal:
        assert not journal.recover()["collection_allowed"]


def test_v3_idle_recovery_does_not_enumerate_or_read_downstream_history(store, monkeypatch):
    with V3Journal(store).locked() as journal:
        capture(journal)
        deliver(journal)
    original = Path.open

    def guarded(path, *args, **kwargs):
        assert not set(path.parts) & {
            "captures",
            "normalization",
            "uploads",
            "confirmations",
            "expiry",
        }
        return original(path, *args, **kwargs)

    def enumeration(path):
        pytest.fail("idle recovery scanned history")

    monkeypatch.setattr(Path, "open", guarded)
    monkeypatch.setattr(Path, "iterdir", enumeration)
    with V3Journal(store).locked() as journal:
        assert journal.recover()["outcomes"]["captured"] == 1


@pytest.mark.parametrize(
    "point",
    [
        "verify_progress_written",
        "verify_progress_replaced",
        "verify_progress_synced",
        "verify_started",
        "verify_capture",
        "verify_result_written",
        "verify_result_replaced",
        "verify_result_synced",
        "verify_report",
    ],
)
def test_v3_verify_crash_never_unlocks_in_progress_scan(store, point):
    with V3Journal(store).locked() as journal:
        capture(journal)
        deliver(journal)
    crash(store, "verify", point)
    with V3Journal(store).locked() as journal:
        assert journal.recover()["collection_allowed"] == (point == "verify_progress_written")
    with V3Verifier(store).locked() as verifier:
        assert verifier.verify()["status"] == "verified"


def test_expiry_cannot_ignore_another_unconfirmed_output_for_the_same_capture(store):
    with V3Journal(store).locked() as journal:
        expired_fixture(journal)
        _, pending, _, _ = records(journal)
        journal.publish_pending(pending.model_copy(update={"name": "another/output.json"}))
    with V3Verifier(store).locked() as verifier:
        with pytest.raises(CaptureError):
            verifier.verify()


@pytest.mark.parametrize(
    "damage", ["cursor_missing", "cursor_hash", "record_gap", "records_symlink"]
)
def test_scope_corruption_blocks_verification(store, damage):
    with V3Journal(store).locked() as journal:
        capture(journal)
        deliver(journal)
    directory = next((store / "normalization").iterdir())
    if damage == "cursor_missing":
        (directory / "cursor.json").unlink()
    elif damage == "cursor_hash":
        (directory / "cursor.json").write_text("{}")
    elif damage == "record_gap":
        next((directory / "records").glob("*.json")).unlink()
    else:
        (directory / "records").rename(directory / "other")
        (directory / "records").symlink_to(directory / "other", target_is_directory=True)
    with V3Verifier(store).locked() as verifier:
        with pytest.raises(CaptureError):
            verifier.verify()


def test_real_cli_selects_v3_and_refuses_default_v2_against_it(store):
    # CLI is real; only the test filesystem boundary is injected for isolated tmpfs.
    program = """import sys
from urbanpulse.adapters import capture_journal
capture_journal.local_filesystem = lambda _: "test-filesystem"
from workers.capture.main import main
raise SystemExit(main())
"""

    def cli(*args):
        return subprocess.run(
            [sys.executable, "-c", program, *args, "--store", str(store)],
            capture_output=True,
            text=True,
            timeout=20,
        )

    result = cli("run", "--store-version", "v3", "--max-attempts", "2", "--max-seconds", "10")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["captured"] == 2
    assert cli("status").returncode == 2
    report = cli("verify", "--store-version", "v3")
    assert report.returncode == 0, report.stdout + report.stderr
    assert json.loads(report.stdout)["retained_payload_bytes"] > 0


@pytest.mark.parametrize(
    "point", ["initialize_written", "initialize_replaced", "initialize_synced", "store_marker"]
)
def test_partial_v3_initialization_never_relabels_or_reinitializes_unknown_data(tmp_path, point):
    crash(tmp_path, "init", point)
    if point == "store_marker":
        with V3Journal(tmp_path).locked() as journal:
            assert journal.recover()["next_capture_sequence"] == 1
    else:
        with pytest.raises(CaptureError, match="store_not_empty"):
            with V3Journal(tmp_path).locked(initialize=True):
                pass

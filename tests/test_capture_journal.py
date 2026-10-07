"""Real Linux filesystem and process-death tests, with no provider credentials."""

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from urbanpulse.adapters import capture_journal as storage
from urbanpulse.adapters.capture_journal import CaptureJournal
from urbanpulse.adapters.synthetic_capture import SyntheticCapture
from urbanpulse.contracts.local_capture import CaptureError, FetchResult

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux fsync/flock contract")
ROOT = Path(__file__).resolve().parents[1]
REAL_FILESYSTEM_CHECK = storage.local_filesystem


@pytest.fixture(autouse=True)
def inject_test_storage(monkeypatch):
    # Ephemeral storage is allowed only by test injection, never a runtime flag.
    monkeypatch.setattr(storage, "local_filesystem", lambda _: "test-filesystem")


@pytest.fixture
def store(tmp_path: Path) -> Path:
    with CaptureJournal(tmp_path).locked(initialize=True):
        pass
    return tmp_path


def capture(journal: CaptureJournal):
    intent = journal.begin("fixture", "vehicle-positions", "test")
    result = SyntheticCapture().fetch("vehicle-positions")
    return intent, result, journal.complete(intent, result)


def test_identical_bytes_distinct_attempts_and_storage_retry(store: Path) -> None:
    with CaptureJournal(store).locked() as journal:
        first, result, manifest = capture(journal)
        assert journal.complete(first, result) == manifest
        second, _, other = capture(journal)
        assert first.capture_id != second.capture_id
        assert manifest.receipt.sha256 == other.receipt.sha256
        payload = store / "captures" / str(first.capture_id) / manifest.receipt.payload_locator
        assert payload.read_bytes() == result.payload
        assert hashlib.sha256(payload.read_bytes()).hexdigest() == manifest.receipt.sha256
        assert journal.recover()["outcomes"]["captured"] == 2
        before = (payload.parent.parent / "manifest.json").read_bytes()
        journal.recover()
        assert (payload.parent.parent / "manifest.json").read_bytes() == before


@pytest.mark.parametrize(
    ("point", "outcome"),
    [
        ("capture_directory", None),
        ("intent", "abandoned"),
        ("payload", "abandoned"),
        ("receipt", "abandoned"),
        ("response", "captured"),
        ("manifest", "captured"),
    ],
)
def test_process_death_at_publication_boundaries(
    store: Path, point: str, outcome: str | None
) -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "tests/helpers/capture_process.py"), str(store), point],
        cwd=ROOT,
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 77, result.stderr.decode()
    with CaptureJournal(store).locked() as journal:
        summary = journal.recover()
        assert sum(summary["outcomes"].values()) == (1 if outcome else 0)
        if outcome:
            assert summary["outcomes"][outcome] == 1
        else:
            assert summary["orphan_directories"] == 1
        assert journal.recover() == summary
    # Recovery made no new intent / upstream attempt.
    assert len(list((store / "captures").iterdir())) == 1


def test_lock_excludes_other_process_and_releases_after_kill(store: Path) -> None:
    child = subprocess.Popen(
        [sys.executable, str(ROOT / "tests/helpers/capture_process.py"), str(store), "hold"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert child.stdout.readline().strip() == "locked"
        with pytest.raises(CaptureError, match="collector_already_running"):
            with CaptureJournal(store).locked():
                pytest.fail("second writer entered")
    finally:
        child.kill()
        child.wait(timeout=10)
    with CaptureJournal(store).locked() as journal:
        assert journal.recover()["outcomes"]["captured"] == 0


def test_missing_marker_and_unknown_directory_are_not_initialized(tmp_path: Path) -> None:
    with pytest.raises(CaptureError, match="store_missing"):
        with CaptureJournal(tmp_path / "missing").locked():
            pass
    with pytest.raises(CaptureError, match="store_marker_invalid"):
        with CaptureJournal(tmp_path).locked():
            pass
    (tmp_path / "unknown").write_bytes(b"preserve me")
    with pytest.raises(CaptureError, match="store_not_empty"):
        with CaptureJournal(tmp_path).locked(initialize=True):
            pass
    assert not (tmp_path / "store.json").exists()


@pytest.mark.parametrize("target", ["payload", "receipt", "manifest", "intent"])
def test_corruption_stops_and_preserves_bytes(store: Path, target: str) -> None:
    with CaptureJournal(store).locked() as journal:
        intent, _, _ = capture(journal)
        directory = store / "captures" / str(intent.capture_id)
        path = {
            "payload": directory / "response/payload.bin",
            "receipt": directory / "response/receipt.json",
            "manifest": directory / "manifest.json",
            "intent": directory / "intent.json",
        }[target]
        path.write_bytes(b"corrupt")
        with pytest.raises(CaptureError, match="integrity_failure"):
            journal.recover()
        assert path.read_bytes() == b"corrupt"


def test_conflicting_storage_retry_cannot_replace_payload(store: Path) -> None:
    with CaptureJournal(store).locked() as journal:
        intent, first, _ = capture(journal)
        changed = FetchResult(first.requested_at, first.received_at, 200, b"different")
        with pytest.raises(CaptureError, match="integrity_failure"):
            journal.complete(intent, changed)
        assert journal.recover()["outcomes"]["captured"] == 1


def test_disk_reserve_stops_before_creating_intent(store: Path, monkeypatch) -> None:
    monkeypatch.setattr(storage.shutil, "disk_usage", lambda _: SimpleNamespace(free=0))
    with CaptureJournal(store).locked() as journal:
        with pytest.raises(CaptureError, match="disk_reserve_reached"):
            journal.begin("fixture", "vehicle-positions", "test")
    assert list((store / "captures").iterdir()) == []


def test_raw_write_failure_is_recorded_and_stops(store: Path, monkeypatch) -> None:
    original = storage.write_bytes

    def fail(path, data):
        if path.name == "payload.bin":
            raise OSError("private path and secret must not escape")
        original(path, data)

    with CaptureJournal(store).locked() as journal:
        intent = journal.begin("fixture", "vehicle-positions", "test")
        monkeypatch.setattr(storage, "write_bytes", fail)
        with pytest.raises(CaptureError, match="^storage_error$"):
            journal.complete(intent, SyntheticCapture().fetch("vehicle-positions"))
        assert journal.recover()["outcomes"]["raw-write-failed"] == 1


def test_published_response_survives_manifest_disk_failure(store: Path, monkeypatch) -> None:
    original = storage.publish_json

    def fail(path, value):
        if path.name == "manifest.json":
            raise OSError("disk failure")
        original(path, value)

    with CaptureJournal(store).locked() as journal:
        intent = journal.begin("fixture", "vehicle-positions", "test")
        with monkeypatch.context() as patch:
            patch.setattr(storage, "publish_json", fail)
            with pytest.raises(CaptureError, match="storage_error"):
                journal.complete(intent, SyntheticCapture().fetch("vehicle-positions"))
        assert journal.recover()["outcomes"]["captured"] == 1


def test_retry_after_survives_restart_and_failure_contains_no_payload(store: Path) -> None:
    with CaptureJournal(store).locked() as journal:
        intent = journal.begin("live", "vehicle-positions", "test")
        now = datetime.now(UTC)
        journal.complete(intent, FetchResult(now, now, 429, None, "http_error", 900))
    with CaptureJournal(store).locked() as journal:
        summary = journal.recover()
        assert summary["outcomes"]["fetch-failed"] == 1
        assert datetime.fromisoformat(summary["retry_not_before"]) > now
    assert list(store.rglob("payload.bin")) == []


def test_session_gap_evidence_is_separate_from_capture_success(store: Path) -> None:
    with CaptureJournal(store).locked() as journal:
        capture(journal)
        summary = journal.recover()
        identity = journal.start_session("fixture", summary)
        journal.end_session(identity, "stopped", 0)
    started = json.loads((store / "sessions" / (str(identity) + ".start.json")).read_bytes())
    assert started["previous_capture_at"] == summary["last_capture_at"]
    ended = json.loads((store / "sessions" / (str(identity) + ".end.json")).read_bytes())
    assert ended["attempts"] == 0 and ended["reason"] == "stopped"


def test_unknown_and_symlink_capture_paths_fail(store: Path) -> None:
    (store / "captures" / str(uuid4())).symlink_to(store, target_is_directory=True)
    with CaptureJournal(store).locked() as journal:
        with pytest.raises(CaptureError, match="integrity_failure"):
            journal.recover()


def test_cli_fixture_roundtrip_and_signal_shutdown(store: Path) -> None:
    command = [sys.executable, str(ROOT / "tests/helpers/capture_process.py"), str(store), "cli"]
    result = subprocess.run(
        [*command, "run", "--store", str(store), "--max-attempts", "3", "--interval", "0.01"],
        capture_output=True,
        text=True,
        timeout=15,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["captured"] == 3
    result = subprocess.run(
        [*command, "status", "--store", str(store)],
        capture_output=True,
        text=True,
        timeout=15,
        cwd=ROOT,
    )
    assert json.loads(result.stdout)["outcomes"]["captured"] == 3
    # Send SIGTERM only after the CLI installs handlers and owns the store.
    child = subprocess.Popen(
        [*command, "run", "--store", str(store), "--interval", "60"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        text=True,
    )
    import time

    try:
        deadline = time.monotonic() + 10
        while len(list((store / "sessions").glob("*.start.json"))) < 2:
            if time.monotonic() > deadline:
                pytest.fail("CLI never started")
            time.sleep(0.02)
        child.terminate()
        output, _ = child.communicate(timeout=15)
        assert child.returncode == 0
        assert json.loads(output)["status"] == "stopped"
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)
    with CaptureJournal(store).locked():
        pass


def test_abandoned_capture_cannot_later_publish_payload(store: Path) -> None:
    with CaptureJournal(store).locked() as journal:
        intent = journal.begin("fixture", "vehicle-positions", "test")
        journal.recover()
        with pytest.raises(CaptureError, match="integrity_failure"):
            journal.complete(intent, SyntheticCapture().fetch("vehicle-positions"))
        assert journal.recover()["outcomes"]["abandoned"] == 1
        assert not (store / "captures" / str(intent.capture_id) / "response").exists()


@pytest.mark.parametrize("filesystem", ["nfs4", "cifs", "fuseblk", "tmpfs", "overlay"])
def test_network_or_foreign_mount_is_refused(tmp_path: Path, monkeypatch, filesystem: str) -> None:
    monkeypatch.setattr(storage, "local_filesystem", REAL_FILESYSTEM_CHECK)
    original = Path.read_text

    def read_mounts(path, *args, **kwargs):
        if str(path) == "/proc/self/mountinfo":
            return "1 0 0:1 / / rw - " + filesystem + " source rw\n"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_mounts)
    with pytest.raises(CaptureError, match="unsupported_filesystem"):
        with CaptureJournal(tmp_path).locked(initialize=True):
            pass
    assert list(tmp_path.iterdir()) == []


def test_session_close_failure_preserves_primary_failure(store: Path, monkeypatch, capsys) -> None:
    from workers.capture.main import main

    def fail_begin(*_):
        raise CaptureError("disk_reserve_reached")

    def fail_end(*_):
        raise OSError("private diagnostic")

    monkeypatch.setattr("workers.capture.main.signal.signal", lambda *_: None)
    monkeypatch.setattr(CaptureJournal, "begin", fail_begin)
    monkeypatch.setattr(CaptureJournal, "end_session", fail_end)
    monkeypatch.setattr(sys, "argv", ["capture", "run", "--store", str(store)])
    assert main() == 2
    output = json.loads(capsys.readouterr().out)
    assert output == {"status": "failed", "reason": "disk_reserve_reached"}


@pytest.mark.parametrize("command", ["init", "run", "status"])
def test_real_cli_rejects_ephemeral_mount(store: Path, command: str) -> None:
    try:
        REAL_FILESYSTEM_CHECK(store)
    except CaptureError:
        pass
    else:
        pytest.skip("Real ephemeral mount exercised in the isolated container suite")
    result = subprocess.run(
        [sys.executable, "-m", "workers.capture.main", command, "--store", str(store)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout) == {"status": "failed", "reason": "unsupported_filesystem"}
    assert list((store / "captures").iterdir()) == []

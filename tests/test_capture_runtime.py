"""Continuous scheduling, reserves and telemetry failure isolation."""

import json
from itertools import pairwise, repeat
from threading import Event

import pytest
from test_local_collector import Clock, Journal, Source

from urbanpulse.adapters.capture_journal import RESERVE_BYTES
from urbanpulse.adapters.capture_runtime import INODE_RESERVE, RuntimeObservation
from urbanpulse.application.local_collector import collect
from urbanpulse.contracts.capture_control import Summary
from urbanpulse.contracts.local_capture import MAX_BYTES, CaptureError


def test_continuous_exceeds_finite_limits_without_resetting_schedule():
    clock, journal, stop = Clock(), Journal(), Event()
    source = Source(clock, repeat(200))
    pulses = []

    def tick():
        pulses.append(clock.now)
        if clock.now >= 7200:
            stop.set()

    result = collect(
        journal,
        source,
        mode="live",
        version="test",
        stop=stop,
        max_attempts=1,
        max_seconds=1,
        interval=15,
        initial_delay=60,
        continuous=True,
        tram_schedule=True,
        tick=tick,
        monotonic=clock.monotonic,
        wait=clock.wait,
    )
    assert result.reason == "stopped" and result.attempts > 120
    assert source.calls[:3] == [
        (60, "vehicle-positions"),
        (75, "trip-updates"),
        (90, "service-alerts"),
    ]
    assert [time for time, feed in source.calls if feed == "trip-updates"] == list(
        range(75, 7200, 120)
    )
    assert max(b - a for a, b in pairwise(pulses)) <= 30


def test_continuous_pulses_during_shared_retry_after_without_extra_requests():
    clock, journal, stop = Clock(), Journal(), Event()
    source = Source(clock, [429], retry_after=600)
    pulses = []

    def tick():
        pulses.append(clock.now)
        if clock.now >= 300:
            stop.set()

    result = collect(
        journal,
        source,
        mode="live",
        version="test",
        stop=stop,
        max_attempts=1,
        max_seconds=1,
        interval=15,
        continuous=True,
        tram_schedule=True,
        tick=tick,
        monotonic=clock.monotonic,
        wait=clock.wait,
    )
    assert result.reason == "stopped" and len(source.calls) == 1
    assert pulses[-1] == 300 and len(pulses) >= 11


@pytest.mark.parametrize("resource", ["bytes", "inodes"])
def test_reserve_refuses_before_any_intent_or_request(tmp_path, resource):
    free = (RESERVE_BYTES + MAX_BYTES + 65536, INODE_RESERVE + 32)
    free = (free[0] - 1, free[1]) if resource == "bytes" else (free[0], free[1] - 1)
    monitor = RuntimeObservation(tmp_path, "fixture", Summary, read_capacity=lambda _: free)
    clock, journal = Clock(), Journal()
    source = Source(clock, [200])
    with pytest.raises(CaptureError, match="reserve_reached"):
        collect(
            journal,
            source,
            mode="fixture",
            version="test",
            stop=Event(),
            max_attempts=1,
            max_seconds=1,
            interval=1,
            before_capture=monitor.guard,
            monotonic=clock.monotonic,
            wait=clock.wait,
        )
    assert not journal.intents and not source.calls
    assert list(tmp_path.iterdir()) == []


def test_heartbeat_failure_does_not_change_capture_and_next_record_reports_failure(tmp_path):
    records = []
    clock, journal = Clock(), Journal()

    def send(line):
        if not records:
            records.append(None)
            raise RuntimeError("private sink detail")
        records.append(json.loads(line))

    monitor = RuntimeObservation(
        tmp_path,
        "fixture",
        Summary,
        read_capacity=lambda _: (10**9, 10000),
        send=send,
        monotonic=clock.monotonic,
    )
    source = Source(clock, [200, 200])
    result = collect(
        journal,
        source,
        mode="fixture",
        version="test",
        stop=Event(),
        max_attempts=2,
        max_seconds=120,
        interval=30,
        tick=monitor.pulse,
        before_capture=monitor.guard,
        after_capture=monitor.completed,
        monotonic=clock.monotonic,
        wait=clock.wait,
    )
    monitor.pulse("stopped", force=True)
    assert result.captured == 2 and monitor.send_failures == 1
    assert records[-1]["send_failures"] == 1 and records[-1]["state"] == "stopped"
    assert records[-1]["session_latest_outcomes"]["trip-updates"] == {"outcome": "captured"}
    assert "private" not in json.dumps(records) and str(tmp_path) not in json.dumps(records)


def test_heartbeat_is_bounded_and_does_not_scan_archive(tmp_path):
    records = []
    monitor = RuntimeObservation(
        tmp_path,
        "live",
        Summary,
        read_capacity=lambda _: (10**9, 10000),
        send=records.append,
        monotonic=lambda: 1,
    )
    for _ in range(10000):
        monitor.pulse()
    assert len(records) == 1
    assert json.loads(records[0])["session_latest_outcomes"] == {}
    assert len(records[0]) < 2048
    assert list(tmp_path.iterdir()) == []


def test_continuous_rejects_v2_before_creating_store(tmp_path, monkeypatch):
    from workers.capture.main import main

    monkeypatch.setattr("sys.argv", ["capture", "serve", "--store", str(tmp_path / "absent")])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2 and not (tmp_path / "absent").exists()


def test_linux_real_cli_crash_restart_and_signal_exit(tmp_path):
    import os
    import signal
    import subprocess
    import sys
    import time
    from pathlib import Path

    if sys.platform != "linux":
        pytest.skip("Linux process and durable-store integration")
    helper = Path(__file__).parent / "helpers" / "capture_process.py"
    prefix = [sys.executable, str(helper), str(tmp_path), "cli"]
    suffix = ["--store", str(tmp_path), "--store-version", "v3"]
    env = os.environ | {"PYTHONUNBUFFERED": "1"}
    init = subprocess.run(
        prefix + ["init"] + suffix, capture_output=True, text=True, timeout=15, env=env
    )
    assert init.returncode == 0, init.stderr
    processes = []
    try:
        for minimum in (2, 3):
            child = subprocess.Popen(
                prefix + ["serve"] + suffix + ["--max-seconds", "1"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            processes.append(child)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                control = json.loads((tmp_path / "control.json").read_text(encoding="utf-8"))
                if control["next_capture_sequence"] >= minimum:
                    break
                assert child.poll() is None
                time.sleep(0.01)
            else:
                pytest.fail("capture did not advance")
            if minimum == 2:
                time.sleep(1.1)
                assert child.poll() is None  # Continuous command ignores finite deadline.
                child.kill()
            else:
                child.send_signal(signal.SIGTERM)
            out, err = child.communicate(timeout=10)
            assert "collector_heartbeat_dry_run" in out, err
            if minimum == 3:
                assert child.returncode == 0, out + err
                assert '"state": "stopped"' in out
        verified = subprocess.run(
            prefix + ["verify"] + suffix, capture_output=True, text=True, timeout=15, env=env
        )
        assert verified.returncode == 0, verified.stdout + verified.stderr
    finally:
        for child in processes:
            if child.poll() is None:
                child.kill()
                child.communicate(timeout=10)


@pytest.mark.parametrize("resource", ["bytes", "inodes"])
def test_linux_reserve_repeated_cli_starts_write_no_sessions(tmp_path, resource):
    import subprocess
    import sys
    from pathlib import Path

    if sys.platform != "linux":
        pytest.skip("Linux durable-store integration")
    helper = Path(__file__).parent / "helpers" / "capture_process.py"
    prefix = [sys.executable, str(helper), str(tmp_path), "cli"]
    suffix = ["--store", str(tmp_path), "--store-version", "v3"]
    init = subprocess.run(prefix + ["init"] + suffix, capture_output=True, text=True, timeout=15)
    assert init.returncode == 0, init.stdout + init.stderr
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    reason = "disk_reserve_reached" if resource == "bytes" else "inode_reserve_reached"
    for _ in range(3):
        result = subprocess.run(
            prefix + ["serve"] + suffix + ["--reserve-" + resource, str(2**63 - 1)],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 78, result.stdout + result.stderr
        records = [json.loads(line) for line in result.stdout.splitlines()]
        assert records[-1] == {"status": "operator_required", "reason": reason}
        assert any(
            record.get("kind") == "collector_heartbeat_dry_run" and record["state"] == reason
            for record in records
        )
        assert list((tmp_path / "sessions").iterdir()) == []
        assert list((tmp_path / "captures").iterdir()) == []
        after = {
            p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()
        }
        assert after == before
    verified = subprocess.run(
        prefix + ["verify"] + suffix, capture_output=True, text=True, timeout=15
    )
    assert verified.returncode == 0, verified.stdout + verified.stderr


@pytest.mark.parametrize("reason", ["disk_reserve_reached", "inode_reserve_reached"])
def test_linux_reserve_reached_during_capture_stops_without_restart_churn(
    tmp_path, monkeypatch, capsys, reason
):
    import sys

    from urbanpulse.adapters import capture_journal as storage
    from urbanpulse.adapters.capture_v3 import V3Journal
    from urbanpulse.adapters.capture_v3_verify import V3Verifier
    from workers.capture import main as worker

    if sys.platform != "linux":
        pytest.skip("Linux durable-store integration")
    monkeypatch.setattr(storage, "local_filesystem", lambda _: "test-filesystem")
    monkeypatch.setattr(worker.signal, "signal", lambda *_: None)
    with V3Journal(tmp_path).locked(initialize=True):
        pass
    clock = Clock()
    real_collect = worker.collect

    def fast_collect(*args, **kwargs):
        return real_collect(*args, **kwargs, monotonic=clock.monotonic, wait=clock.wait)

    monkeypatch.setattr(worker, "collect", fast_collect)
    checks = 0

    def guard(_):
        nonlocal checks
        checks += 1
        if checks >= 3:
            raise CaptureError(reason)

    monkeypatch.setattr(worker.RuntimeObservation, "guard", guard)
    monkeypatch.setattr(
        "sys.argv", ["capture", "serve", "--store", str(tmp_path), "--store-version", "v3"]
    )
    assert worker.main() == 78
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert records[-1] == {"status": "operator_required", "reason": reason}
    assert any(record.get("state") == reason for record in records)
    assert len(list((tmp_path / "captures").iterdir())) == 1
    sessions = {p.name: p.read_bytes() for p in (tmp_path / "sessions").iterdir()}
    assert len(sessions) == 2  # Only the original session is closed once.
    for _ in range(3):
        assert worker.main() == 78
        assert {p.name: p.read_bytes() for p in (tmp_path / "sessions").iterdir()} == sessions
    with V3Verifier(tmp_path).locked() as verifier:
        assert verifier.verify()["status"] == "verified"

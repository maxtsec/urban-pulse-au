"""Operator failures do not expose database credentials or arbitrary exception text."""

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from urbanpulse.application.durable_delivery import StorageUnavailable
from urbanpulse.application.event_worker import WorkerResult
from workers.events.main import poll

ROOT = Path(__file__).parents[2]


@pytest.mark.parametrize("command", [["metrics"], ["run", "--once"]])
def test_database_unavailable_exits_nonzero_without_credentials(command):
    secret = "private-test-password"
    env = dict(
        os.environ,
        DATABASE_URL=f"postgresql://probe:{secret}@127.0.0.1:1/unavailable?connect_timeout=2",
    )
    result = subprocess.run(
        [sys.executable, "-m", "workers.events.main", *command],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout) == {"error": "database-unavailable-or-schema-invalid"}
    assert secret not in result.stdout + result.stderr
    assert not result.stderr


@pytest.mark.parametrize("option,value", [("--poll-seconds", "nan"), ("--lease-seconds", "0")])
def test_bad_worker_timing_is_rejected_before_database_access(option, value):
    result = subprocess.run(
        [sys.executable, "-m", "workers.events.main", "run", "--once", option, value],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2
    assert "poll interval" in result.stderr


def test_polling_backs_off_to_a_cap_resets_after_recovery_and_honors_stop(monkeypatch, capsys):
    stop = threading.Event()
    waits = []
    monkeypatch.setattr(stop, "wait", lambda seconds: waits.append(seconds))
    outcomes = [StorageUnavailable("secret") for _ in range(8)]
    outcomes += [WorkerResult("idle"), StorageUnavailable("secret"), WorkerResult("apply")]

    class Worker:
        def step(self):
            result = outcomes.pop(0)
            if not outcomes:
                stop.set()
            if isinstance(result, Exception):
                raise result
            return result

    poll(Worker(), stop, once=False, interval=0.25)
    assert waits == [1, 2, 4, 8, 16, 30, 30, 30, 0.25, 1]
    output = capsys.readouterr().out
    assert "secret" not in output
    assert json.loads(output.splitlines()[-1])["status"] == "apply"


def test_stop_during_database_backoff_prevents_another_poll(monkeypatch):
    stop = threading.Event()
    calls = []
    monkeypatch.setattr(stop, "wait", lambda seconds: stop.set())

    class Worker:
        def step(self):
            calls.append(1)
            raise StorageUnavailable("offline")

    poll(Worker(), stop, once=False, interval=0.25)
    assert calls == [1]

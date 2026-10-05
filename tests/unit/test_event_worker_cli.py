"""Operator failures do not expose database credentials or arbitrary exception text."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

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

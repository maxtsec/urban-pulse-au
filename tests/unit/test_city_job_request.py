"""Validate finite job requests before starting a child or touching a database."""

import threading
from unittest.mock import MagicMock

import pytest

from workers.city.job import JobRequest, child, supervise


@pytest.mark.parametrize(
    "field,value",
    [
        ("run_id", "../invalid"),
        ("scope", "not-an-import"),
        ("scenario", "live"),
        ("seconds", -1),
        ("seconds", 361),
        ("seconds", True),
        ("timeout_seconds", 0),
        ("timeout_seconds", 541),
        ("timeout_seconds", True),
    ],
)
def test_invalid_job_arguments_fail_before_execution(field, value):
    values = dict(run_id="demo", scope="a" * 64, scenario="city", seconds=360)
    values[field] = value
    with pytest.raises(ValueError):
        JobRequest(**values)


def test_already_cancelled_job_does_not_start_a_process(monkeypatch):
    def forbidden(*args):
        pytest.fail("cancelled invocation must not spawn work")

    monkeypatch.setattr("workers.city.job.multiprocessing.get_context", forbidden)
    stop = threading.Event()
    stop.set()
    assert supervise(JobRequest("demo", "a" * 64, "city", 0), stop) == "interrupted"


def test_child_returns_only_redacted_configuration_failure(monkeypatch):
    monkeypatch.setenv("CACHE_ENABLED", "synthetic-sensitive-invalid-value")
    output = MagicMock()
    child(JobRequest("demo", "a" * 64, "city", 0), 0, output)
    output.send.assert_called_once_with("invalid-configuration")
    output.close.assert_called_once_with()

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


@pytest.mark.parametrize("result", ["complete", "dead-letter"])
def test_finished_child_result_wins_over_late_parent_observation(monkeypatch, result):
    runtime = MagicMock()
    incoming, outgoing = MagicMock(), MagicMock()
    runtime.Pipe.return_value = incoming, outgoing
    process = runtime.Process.return_value
    process.is_alive.return_value = False
    process.exitcode = 0
    incoming.poll.return_value = True
    incoming.recv.return_value = result
    monkeypatch.setattr("workers.city.job.multiprocessing.get_context", lambda _: runtime)
    monkeypatch.setattr("workers.city.job.time.monotonic", MagicMock(side_effect=[0, 541]))
    assert supervise(JobRequest("demo", "a" * 64, "city", 0), threading.Event()) == result
    process.terminate.assert_not_called()
    incoming.close.assert_called_once()


@pytest.mark.parametrize("has_result", [False, True])
def test_expired_job_without_a_readable_result_is_still_timeout(monkeypatch, has_result):
    runtime = MagicMock()
    incoming, outgoing = MagicMock(), MagicMock()
    runtime.Pipe.return_value = incoming, outgoing
    process = runtime.Process.return_value
    process.is_alive.return_value = False
    process.exitcode = 0
    incoming.poll.return_value = has_result
    incoming.recv.side_effect = EOFError
    monkeypatch.setattr("workers.city.job.multiprocessing.get_context", lambda _: runtime)
    monkeypatch.setattr("workers.city.job.time.monotonic", MagicMock(side_effect=[0, 541]))
    assert (
        supervise(JobRequest("demo", "a" * 64, "city", 0), threading.Event()) == "deadline-exceeded"
    )


def test_child_exit_during_deadline_check_preserves_its_result(monkeypatch):
    runtime = MagicMock()
    incoming, outgoing = MagicMock(), MagicMock()
    runtime.Pipe.return_value = incoming, outgoing
    process = runtime.Process.return_value
    process.is_alive.side_effect = [True, False, False, False]
    process.exitcode = 0
    incoming.poll.return_value = True
    incoming.recv.return_value = "complete"
    monkeypatch.setattr("workers.city.job.multiprocessing.get_context", lambda _: runtime)
    monkeypatch.setattr("workers.city.job.time.monotonic", MagicMock(side_effect=[0, 541]))
    assert supervise(JobRequest("demo", "a" * 64, "city", 0), threading.Event()) == "complete"
    process.terminate.assert_not_called()

"""Shared finite-process supervision and redacted results for private demo Jobs."""

import multiprocessing
import threading
import time
from collections.abc import Callable
from multiprocessing.connection import Connection
from typing import Protocol

import psycopg
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from urbanpulse.adapters.job_database import JobBusy, JobSessionLost
from urbanpulse.application.durable_delivery import StorageUnavailable


class TimedRequest(Protocol):
    @property
    def timeout_seconds(self) -> int: ...


def report(operation: Callable[[], dict[str, str]], output: Connection) -> None:
    try:
        result = operation()
    except JobBusy:
        result = {"status": "busy"}
    except JobSessionLost:
        result = {"status": "session-lost"}
    except (StorageUnavailable, SQLAlchemyError, psycopg.Error, OSError):
        result = {"status": "database-unavailable"}
    except ValidationError:
        result = {"status": "invalid-configuration"}
    except (ValueError, LookupError):
        result = {"status": "invalid-run-or-inputs"}
    except Exception:
        result = {"status": "execution-failed"}
    try:
        output.send(result)
    finally:
        output.close()


def supervise(
    request: TimedRequest, stop: threading.Event, target: Callable[..., None]
) -> dict[str, str]:
    if stop.is_set():
        return {"status": "interrupted"}
    deadline = time.monotonic() + request.timeout_seconds
    runtime = multiprocessing.get_context("spawn")
    incoming, outgoing = runtime.Pipe(duplex=False)
    process = runtime.Process(target=target, args=(request, deadline, outgoing))
    started = False
    try:
        process.start()
        started = True
        outgoing.close()
        while process.is_alive():
            if stop.is_set():
                return {"status": "interrupted"}
            if time.monotonic() >= deadline:
                # The child may have exited since is_alive() was checked above.
                if process.is_alive():
                    return {"status": "deadline-exceeded"}
                break
            process.join(timeout=0.05)
        if stop.is_set():
            return {"status": "interrupted"}
        # A completed child result takes precedence over late observation by the parent.
        if process.exitcode == 0 and incoming.poll():
            try:
                result = incoming.recv()
                if (
                    isinstance(result, dict)
                    and isinstance(result.get("status"), str)
                    and all(isinstance(k, str) and isinstance(v, str) for k, v in result.items())
                ):
                    return result
                return {"status": "execution-failed"}
            except EOFError:
                pass
        if time.monotonic() >= deadline:
            return {"status": "deadline-exceeded"}
        return {"status": "execution-failed"}
    finally:
        # Terminate only the child owned by this invocation; keep cleanup below the task deadline.
        if started:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
            if process.is_alive():
                process.kill()
                process.join(timeout=5)
            process.close()
        incoming.close()
        outgoing.close()

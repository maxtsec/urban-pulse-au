"""Finite, manually invoked fixture worker; success means the selected target is delivered."""

import argparse
import multiprocessing
import signal
import threading
import time
from dataclasses import dataclass
from multiprocessing.connection import Connection

import psycopg
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from urbanpulse.adapters.city_runs import PostgresCityRuns, context
from urbanpulse.adapters.city_store import CityInputStore
from urbanpulse.adapters.event_recovery import PostgresRecoveryStore
from urbanpulse.adapters.job_database import JobBusy, JobDatabase, JobSessionLost
from urbanpulse.adapters.postgis import PostgisMembership
from urbanpulse.application.city import MAX_SECONDS
from urbanpulse.application.city_checkpoints import CONSUMER, RESULT_CONSUMER
from urbanpulse.application.durable_delivery import StorageUnavailable
from urbanpulse.application.event_worker import EventWorker
from urbanpulse.application.scenarios import Scenario
from urbanpulse.config import Settings
from workers.runtime import emit


@dataclass(frozen=True)
class JobRequest:
    run_id: str
    scope: str
    scenario: str
    seconds: int
    timeout_seconds: int = 540

    def __post_init__(self) -> None:
        context(self.run_id)
        if len(self.scope) != 64 or any(char not in "0123456789abcdef" for char in self.scope):
            raise ValueError("scope must be an import hash")
        Scenario(self.scenario)
        if type(self.seconds) is not int or not 0 <= self.seconds <= MAX_SECONDS:
            raise ValueError("target outside fixture clock")
        if type(self.timeout_seconds) is not int or not 1 <= self.timeout_seconds <= 540:
            raise ValueError("timeout must be 1 to 540 seconds")


def execute(request: JobRequest, deadline: float) -> str:
    database = JobDatabase(Settings().database_url)
    try:
        queue = PostgresRecoveryStore(database.engine, claim_context=context(request.run_id))
        city = PostgresCityRuns(
            queue,
            CityInputStore(database.engine),
            PostgisMembership("", engine=database.engine),
        )
        city.create(request.run_id, request.scope, request.scenario)
        existing = city.read_run(request.run_id)
        # Preserve recorded failures on a repeated invocation; only operator recovery clears them.
        state = city.job_status(request.run_id, existing["target"])
        if state in ("dead-letter", "checkpoint-error"):
            return state
        if state == "complete" and existing["target"] == request.seconds:
            return state
        city.advance(request.run_id, request.seconds)
        inputs = EventWorker(queue, CONSUMER, city.receive)
        results = EventWorker(queue, RESULT_CONSUMER, city.receive)
        while time.monotonic() < deadline:
            state = city.job_status(request.run_id, request.seconds)
            if state != "pending":
                return state
            progressed = city.finish(request.run_id)
            incoming = inputs.step()
            outgoing = results.step()
            if not progressed and incoming.status == outgoing.status == "idle":
                time.sleep(min(0.1, max(0, deadline - time.monotonic())))
        return "deadline-exceeded"
    finally:
        database.close()


def child(request: JobRequest, deadline: float, output: Connection) -> None:
    try:
        status = execute(request, deadline)
    except JobBusy:
        status = "busy"
    except JobSessionLost:
        status = "session-lost"
    except (StorageUnavailable, SQLAlchemyError, psycopg.Error, OSError):
        status = "database-unavailable"
    except ValidationError:
        status = "invalid-configuration"
    except (ValueError, LookupError):
        status = "invalid-run-or-inputs"
    except Exception:
        # Never forward exception text, connection strings or fixture payloads to logs.
        status = "execution-failed"
    try:
        output.send(status)
    finally:
        output.close()


def supervise(request: JobRequest, stop: threading.Event) -> str:
    if stop.is_set():
        return "interrupted"
    deadline = time.monotonic() + request.timeout_seconds
    runtime = multiprocessing.get_context("spawn")
    incoming, outgoing = runtime.Pipe(duplex=False)
    process = runtime.Process(target=child, args=(request, deadline, outgoing))
    started = False
    try:
        process.start()
        started = True
        outgoing.close()
        while process.is_alive():
            if stop.is_set():
                return "interrupted"
            if time.monotonic() >= deadline:
                # The child may have exited since is_alive() was checked above.
                if process.is_alive():
                    return "deadline-exceeded"
                break
            process.join(timeout=0.05)
        if stop.is_set():
            return "interrupted"
        # A completed child result takes precedence over late observation by the parent.
        if process.exitcode == 0 and incoming.poll():
            try:
                return str(incoming.recv())
            except EOFError:
                pass
        if time.monotonic() >= deadline:
            return "deadline-exceeded"
        return "execution-failed"
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id")
    parser.add_argument("--scope", required=True)
    parser.add_argument("--scenario", choices=list(Scenario), default="city")
    parser.add_argument("--seconds", type=int, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=540)
    args = parser.parse_args()
    try:
        request = JobRequest(
            args.run_id, args.scope, args.scenario, args.seconds, args.timeout_seconds
        )
    except ValueError:
        emit({"status": "invalid-job-arguments"})
        return 2
    stop = threading.Event()

    def stopping(signum: int, frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, stopping)
    signal.signal(signal.SIGINT, stopping)
    try:
        status = supervise(request, stop)
    except Exception:
        status = "execution-failed"
    emit({"status": status, "run_id": request.run_id, "target_seconds": request.seconds})
    return 0 if status == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())

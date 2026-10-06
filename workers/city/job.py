"""Finite, manually invoked fixture worker; success means the selected target is delivered."""

import argparse
import signal
import threading
import time
from dataclasses import dataclass
from multiprocessing.connection import Connection

from urbanpulse.adapters.city_runs import PostgresCityRuns, context
from urbanpulse.adapters.city_store import CityInputStore
from urbanpulse.adapters.event_recovery import PostgresRecoveryStore
from urbanpulse.adapters.job_database import JobDatabase
from urbanpulse.adapters.postgis import PostgisMembership
from urbanpulse.application.city import MAX_SECONDS
from urbanpulse.application.city_checkpoints import CONSUMER, RESULT_CONSUMER
from urbanpulse.application.event_worker import EventWorker
from urbanpulse.application.scenarios import Scenario
from urbanpulse.config import Settings
from workers.job_runtime import report
from workers.job_runtime import supervise as supervise_process
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
    report(lambda: {"status": execute(request, deadline)}, output)


def supervise(request: JobRequest, stop: threading.Event) -> str:
    return supervise_process(request, stop, child)["status"]


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

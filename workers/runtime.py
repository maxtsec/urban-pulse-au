"""Shared polling and sanitized console output for independent worker entry points."""

import json
import threading
from dataclasses import asdict
from typing import Protocol

from sqlalchemy.exc import SQLAlchemyError

from urbanpulse.application.durable_delivery import StorageUnavailable
from urbanpulse.application.event_worker import WorkerResult


def emit(value: object) -> None:
    print(json.dumps(value, default=str), flush=True)


class PollingWorker(Protocol):
    def step(self) -> WorkerResult: ...


def poll(worker: PollingWorker, stop: threading.Event, *, once: bool, interval: float) -> None:
    backoff = 1.0
    while not stop.is_set():
        try:
            result = worker.step()
        except (StorageUnavailable, SQLAlchemyError):
            if once:
                raise
            emit({"error": "database-unavailable", "retry_in_seconds": backoff})
            stop.wait(backoff)
            backoff = min(backoff * 2, 30)
            continue
        backoff = 1.0
        if result.status != "idle" or once:
            emit(asdict(result))
        if once:
            return
        if result.status == "idle":
            stop.wait(interval)

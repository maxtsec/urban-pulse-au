"""Bounded synchronous delivery; no durable notification or external side effects."""

import json
import logging
from collections.abc import Callable, Sequence
from time import sleep

from urbanpulse.application.delivery import (
    CompositionUnavailable,
    Handler,
    HandlerResult,
    RetryableHandlerError,
)

logger = logging.getLogger(__name__)


class InProcessPublisher:
    def __init__(self, context: str, sleeper: Callable[[float], None] = sleep) -> None:
        self.context = context
        self.sleeper = sleeper
        self.attempts: list[dict[str, object]] = []

    def publish(self, wire: str, handlers: Sequence[Handler]) -> dict[str, HandlerResult]:
        results = {}
        if len({handler.name for handler in handlers}) != len(handlers):
            raise ValueError("handler names must be unique")
        try:
            envelope = json.loads(wire)
            identity = {"source": envelope.get("source"), "event_id": envelope.get("id")}
        except (ValueError, AttributeError):
            identity = {"source": None, "event_id": None}
        for handler in handlers:
            for attempt in range(1, 4):
                try:
                    result = handler.handle(wire)
                except RetryableHandlerError:
                    result = HandlerResult("retryable-failure", "transient-handler-failure")
                diagnostic = {
                    "context": self.context,
                    "handler": handler.name,
                    **identity,
                    "attempt": attempt,
                    "outcome": result.outcome,
                    "reason": result.reason,
                }
                self.attempts.append(diagnostic)
                if result.outcome != "retryable-failure":
                    results[handler.name] = result
                    break
                if attempt == 3:
                    logger.warning("composition_failed %s", json.dumps(diagnostic, sort_keys=True))
                    raise CompositionUnavailable(
                        "handler retries exhausted; reconstruct from persisted inputs"
                    )
                self.sleeper((0.1, 0.25)[attempt - 1])
        return results

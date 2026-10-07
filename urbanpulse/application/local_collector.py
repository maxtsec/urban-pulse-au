"""One bounded capture loop with a shared request budget and stop-aware waits."""

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Event

from urbanpulse.application.tram_schedule import TramSchedule
from urbanpulse.contracts.local_capture import FEEDS, Journal, Mode, Source


@dataclass(frozen=True)
class CollectionResult:
    attempts: int
    captured: int
    reason: str


def collect(
    journal: Journal,
    source: Source,
    *,
    mode: Mode,
    version: str,
    stop: Event,
    max_attempts: int,
    max_seconds: float,
    interval: float,
    initial_delay: float = 0,
    tram_schedule: bool = False,
    monotonic: Callable[[], float] = time.monotonic,
    wait: Callable[[float], bool] | None = None,
) -> CollectionResult:
    """No catch-up burst. Retry and scheduled polls consume the same finite budget."""
    if not 1 <= max_attempts <= 120 or not 1 <= max_seconds <= 3600:
        raise ValueError("invalid_collection_limits")
    if not math.isfinite(interval) or interval < (15 if mode == "live" else 0.01):
        raise ValueError("invalid_request_interval")
    wait = wait or stop.wait
    deadline = monotonic() + max_seconds
    attempts = captured = feed_index = failures = 0
    delay = max(initial_delay, 0)
    schedule = TramSchedule(monotonic() + delay, max(15, interval)) if tram_schedule else None
    while attempts < max_attempts:
        if schedule is not None:
            feed, due = schedule.next(monotonic())
            delay = max(0, due - monotonic())
        else:
            feed = FEEDS[feed_index]
        remaining = deadline - monotonic()
        if remaining <= 0:
            return CollectionResult(attempts, captured, "duration_limit")
        if stop.is_set() or wait(min(delay, remaining)):
            return CollectionResult(attempts, captured, "stopped")
        if monotonic() >= deadline:
            return CollectionResult(attempts, captured, "duration_limit")
        intent = journal.begin(mode, feed, version)
        started = monotonic()
        result = source.fetch(feed)
        manifest = journal.complete(intent, result)
        attempts += 1
        delay = interval
        if manifest.outcome == "captured":
            captured += 1
            failures = 0
            feed_index = (feed_index + 1) % len(FEEDS)
        else:
            # A 200 response can still fail during body transfer. Only classify
            # an actual HTTP rejection by status; retry bounded body failures.
            if (
                result.reason == "http_error"
                and result.http_status is not None
                and result.http_status < 500
                and result.http_status != 429
            ):
                return CollectionResult(attempts, captured, "source_rejected")
            failures += 1
            delay = max(interval, min(300, 15 * 2 ** min(failures - 1, 5)))
        if result.retry_after_seconds is not None:
            delay = max(delay, result.retry_after_seconds)
        if manifest.retry_not_before is not None:
            delay = max(delay, (manifest.retry_not_before - datetime.now(UTC)).total_seconds())
        if schedule is not None:
            cooldown = max(0, result.retry_after_seconds or 0)
            if manifest.retry_not_before is not None:
                cooldown = max(
                    cooldown, (manifest.retry_not_before - datetime.now(UTC)).total_seconds()
                )
            schedule.completed(feed, started, monotonic(), manifest.outcome == "captured", cooldown)
    return CollectionResult(attempts, captured, "attempt_limit")

"""Finite or continuous capture with shared request spacing and stop-aware waits."""

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Event

from urbanpulse.application.tram_schedule import TramSchedule
from urbanpulse.contracts.local_capture import FEEDS, Intent, Journal, Manifest, Mode, Source


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
    continuous: bool = False,
    tick: Callable[[], None] = lambda: None,
    before_capture: Callable[[], None] = lambda: None,
    after_capture: Callable[[Intent, Manifest], None] = lambda *_: None,
    monotonic: Callable[[], float] = time.monotonic,
    wait: Callable[[float], bool] | None = None,
) -> CollectionResult:
    """No catch-up burst. Continuous mode retains the same scheduler until stopped."""
    if not 1 <= max_attempts <= 120 or not 1 <= max_seconds <= 3600:
        raise ValueError("invalid_collection_limits")
    if not math.isfinite(interval) or interval < (15 if mode == "live" else 0.01):
        raise ValueError("invalid_request_interval")
    wait = wait or stop.wait
    deadline = math.inf if continuous else monotonic() + max_seconds
    attempts = captured = feed_index = failures = 0
    delay = max(initial_delay, 0)
    schedule = TramSchedule(monotonic() + delay, max(15, interval)) if tram_schedule else None
    while continuous or attempts < max_attempts:
        if schedule is not None:
            feed, due = schedule.next(monotonic())
            delay = max(0, due - monotonic())
        else:
            feed = FEEDS[feed_index]
        remaining = deadline - monotonic()
        if remaining <= 0:
            return CollectionResult(attempts, captured, "duration_limit")
        wake_at = monotonic() + min(delay, remaining)
        while True:
            tick()
            if stop.is_set():
                return CollectionResult(attempts, captured, "stopped")
            sleep_for = max(0, wake_at - monotonic())
            if wait(min(sleep_for, 30) if continuous else sleep_for):
                return CollectionResult(attempts, captured, "stopped")
            if monotonic() >= wake_at:
                break
        if monotonic() >= deadline:
            return CollectionResult(attempts, captured, "duration_limit")
        before_capture()
        intent = journal.begin(mode, feed, version)
        started = monotonic()
        result = source.fetch(feed)
        manifest = journal.complete(intent, result)
        after_capture(intent, manifest)
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

"""Deterministic scheduling tests exercise limits, retries and stop handling."""

from datetime import UTC, datetime
from threading import Event
from types import SimpleNamespace
from uuid import uuid4

import pytest

from urbanpulse.application.local_collector import collect
from urbanpulse.contracts.local_capture import FetchResult, Intent


class Clock:
    now = 0.0

    def monotonic(self):
        return self.now

    def wait(self, seconds):
        self.now += seconds
        return False


class Journal:
    def __init__(self):
        self.intents = []

    def begin(self, mode, feed, version):
        intent = Intent(
            capture_id=uuid4(),
            mode=mode,
            provider="synthetic",
            product=feed,
            requested_at=datetime.now(UTC),
            collector_version=version,
        )
        self.intents.append(intent)
        return intent

    def complete(self, intent, result):
        return SimpleNamespace(
            outcome="captured" if result.payload is not None else "fetch-failed",
            retry_not_before=None,
        )


class Source:
    def __init__(self, clock, statuses, retry_after=None):
        self.clock, self.statuses, self.retry_after = clock, iter(statuses), retry_after
        self.calls = []

    def fetch(self, feed):
        self.calls.append((self.clock.now, feed))
        status = next(self.statuses)
        now = datetime.now(UTC)
        return FetchResult(
            now,
            now,
            status,
            b"fixture" if status == 200 else None,
            None if status == 200 else "http_error",
            self.retry_after,
        )


def run(statuses, *, attempts=4, seconds=1000, retry_after=None, stop=None):
    clock, journal = Clock(), Journal()
    source = Source(clock, statuses, retry_after)
    result = collect(
        journal,
        source,
        mode="live",
        version="test",
        stop=stop or Event(),
        max_attempts=attempts,
        max_seconds=seconds,
        interval=15,
        monotonic=clock.monotonic,
        wait=clock.wait,
    )
    return result, source.calls, journal.intents


def test_retries_share_budget_and_backoff_across_feeds():
    result, calls, intents = run([503, 503, 200, 200])
    assert result.attempts == 4 and result.captured == 2
    assert [instant for instant, _ in calls] == [0, 15, 45, 60]
    assert [feed for _, feed in calls] == ["vehicle-positions"] * 3 + ["trip-updates"]
    assert len({intent.capture_id for intent in intents}) == 4


def test_retry_after_cannot_be_shortened_by_duration_limit():
    result, calls, _ = run([429], seconds=60, retry_after=120)
    assert result.reason == "duration_limit"
    assert len(calls) == 1


@pytest.mark.parametrize("status", [301, 401, 403, 404])
def test_permanent_failure_stops_without_retry(status):
    result, calls, _ = run([status])
    assert result.reason == "source_rejected"
    assert len(calls) == 1


def test_stop_before_intent_does_not_fetch():
    stop = Event()
    stop.set()
    result, calls, intents = run([], stop=stop)
    assert result.reason == "stopped" and calls == [] and intents == []


def test_three_feeds_are_served_under_one_budget():
    result, calls, _ = run([200] * 4)
    assert result.reason == "attempt_limit"
    assert [feed for _, feed in calls] == [
        "vehicle-positions",
        "trip-updates",
        "service-alerts",
        "vehicle-positions",
    ]


def test_initial_cooldown_cannot_fetch_after_deadline():
    clock, journal = Clock(), Journal()
    source = Source(clock, [])
    result = collect(
        journal,
        source,
        mode="live",
        version="test",
        stop=Event(),
        max_attempts=1,
        max_seconds=30,
        interval=15,
        initial_delay=60,
        monotonic=clock.monotonic,
        wait=clock.wait,
    )
    assert result.reason == "duration_limit" and not source.calls

"""Deterministic scheduling tests exercise limits, retries and stop handling."""

from datetime import UTC, datetime
from itertools import pairwise
from threading import Event
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from urbanpulse.adapters import transport_capture as transport
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


def scheduled_run(
    statuses, *, attempts=10, seconds=1000, retry_after=None, fetch_seconds=0, jitter=0
):
    clock, journal = Clock(), Journal()
    source = Source(clock, statuses, retry_after)
    fetch = source.fetch

    def slow_fetch(feed):
        result = fetch(feed)
        clock.now += fetch_seconds
        return result

    source.fetch = slow_fetch

    def wait(seconds):
        clock.now += seconds + jitter
        return False

    result = collect(
        journal,
        source,
        mode="live",
        version="test",
        stop=Event(),
        max_attempts=attempts,
        max_seconds=seconds,
        interval=15,
        initial_delay=60,
        tram_schedule=True,
        monotonic=clock.monotonic,
        wait=wait,
    )
    return result, source.calls


def test_accepted_schedule_has_differentiated_cadence_and_one_shared_start_budget():
    result, calls = scheduled_run([200] * 10)
    assert result.attempts == 10
    assert calls == [
        (60, "vehicle-positions"),
        (75, "trip-updates"),
        (90, "service-alerts"),
        (120, "vehicle-positions"),
        (150, "service-alerts"),
        (180, "vehicle-positions"),
        (195, "trip-updates"),
        (210, "service-alerts"),
        (240, "vehicle-positions"),
        (270, "service-alerts"),
    ]
    for start, _ in calls:
        assert sum(start <= instant < start + 60 for instant, _ in calls) <= 4
    assert all(b[0] - a[0] >= 15 for a, b in pairwise(calls))


def test_scheduled_failed_feed_does_not_starve_other_feeds():
    result, calls = scheduled_run([503, 200, 200, 503, 200, 503, 200, 200, 503, 200])
    assert result.captured == 6
    assert [time for time, feed in calls if feed == "trip-updates"] == [75, 195]
    assert [time for time, feed in calls if feed == "service-alerts"] == [90, 150, 210, 270]


def test_scheduled_retry_after_is_shared_and_missed_slots_are_not_replayed():
    result, calls = scheduled_run([429, 200, 200], attempts=3, retry_after=121)
    assert result.attempts == 3
    assert calls[0] == (60, "vehicle-positions")
    assert calls[1] == (181, "vehicle-positions")
    assert calls[2][0] >= calls[1][0] + 121


def test_slow_responses_skip_missed_slots_instead_of_bursting():
    _, calls = scheduled_run([200] * 4, attempts=4, fetch_seconds=31)
    assert calls == [
        (60, "vehicle-positions"),
        (91, "service-alerts"),
        (122, "vehicle-positions"),
        (153, "service-alerts"),
    ]


def test_scheduler_tolerates_real_wakeup_jitter_without_losing_each_next_slot():
    _, calls = scheduled_run([200] * 10, jitter=0.004, fetch_seconds=0.3)
    assert [feed for _, feed in calls].count("vehicle-positions") == 4
    assert [feed for _, feed in calls].count("trip-updates") == 2
    assert [feed for _, feed in calls].count("service-alerts") == 4
    assert all(b[0] - a[0] >= 15 for a, b in pairwise(calls))
    assert calls[-1][0] < 271


def test_scheduled_permanent_rejection_and_startup_deadline_still_stop():
    result, calls = scheduled_run([403])
    assert result.reason == "source_rejected" and len(calls) == 1
    result, calls = scheduled_run([], seconds=30)
    assert result.reason == "duration_limit" and not calls


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


@pytest.mark.parametrize("failure", ["network_error", "time_limit", "size_limit", "encoding"])
def test_failure_after_200_retries_with_backoff_and_new_identity(failure, monkeypatch):
    clock, journal = Clock(), Journal()
    requested = []
    fetch_times = []
    monotonic_values = iter([0.0, 16.0, 30.0, 30.0, 30.0, 30.0])
    monkeypatch.setattr(transport.time, "monotonic", lambda: next(monotonic_values))
    if failure == "size_limit":
        monkeypatch.setattr(transport, "MAX_BYTES", 4)

    class BrokenBody(httpx.SyncByteStream):
        def __iter__(self):
            yield b"part"
            raise httpx.ReadError("redacted connection failure")

    def handler(request):
        requested.append(request.url.path)
        fetch_times.append(clock.now)
        if len(requested) == 1:
            if failure == "network_error":
                return httpx.Response(200, stream=BrokenBody())
            if failure == "encoding":
                return httpx.Response(
                    200, headers={"content-encoding": "gzip"}, stream=httpx.ByteStream(b"payload")
                )
            return httpx.Response(200, stream=httpx.ByteStream(b"oversized"))
        return httpx.Response(200, stream=httpx.ByteStream(b"ok"))

    # Network/size/encoding cases should not hit the elapsed-time guard first.
    if failure != "time_limit":
        monkeypatch.setattr(transport.time, "monotonic", lambda: 0.0)
    outcomes = []
    complete = journal.complete

    def record(intent, result):
        outcomes.append(result)
        return complete(intent, result)

    journal.complete = record
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = collect(
            journal,
            transport.TransportCapture(client, SecretStr("synthetic-secret")),
            mode="live",
            version="test",
            stop=Event(),
            max_attempts=2,
            max_seconds=120,
            interval=15,
            monotonic=clock.monotonic,
            wait=clock.wait,
        )
    assert result.reason == "attempt_limit" and result.captured == 1
    assert outcomes[0].http_status == 200 and outcomes[0].reason == failure
    assert outcomes[0].payload is None
    assert fetch_times == [0.0, 15.0] and requested[0] == requested[1]
    assert journal.intents[0].capture_id != journal.intents[1].capture_id

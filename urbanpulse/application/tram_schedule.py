"""Accepted serialized tram slots; delayed work never becomes a catch-up queue."""

import math

from urbanpulse.contracts.local_capture import TramFeed

SLOTS: tuple[tuple[TramFeed, int, int], ...] = (
    ("vehicle-positions", 0, 60),
    ("trip-updates", 15, 120),
    ("service-alerts", 30, 60),
)


class TramSchedule:
    def __init__(self, anchor: float, spacing: float) -> None:
        self.spacing = spacing
        self.available = anchor
        self.due = {feed: anchor + phase for feed, phase, _ in SLOTS}
        self.failures = {feed: 0 for feed, _, _ in SLOTS}
        self.blocked = {feed: anchor for feed, _, _ in SLOTS}

    def next(self, now: float) -> tuple[TramFeed, float]:
        candidates: list[tuple[float, int, TramFeed]] = []
        for rank, (feed, _, period) in enumerate(SLOTS):
            earliest = max(now, self.available, self.blocked[feed])
            due = self.due[feed]
            # A slot remains usable for 15 seconds: OS wakeup/fsync jitter must
            # not skip a whole period. Older slots expire rather than queue.
            if due + 15 <= earliest:
                due += (math.floor((earliest - due - 15) / period) + 1) * period
            candidates.append((max(due, earliest), rank, feed))
        due, _, feed = min(candidates)
        return feed, due

    def completed(
        self, feed: TramFeed, started: float, finished: float, success: bool, cooldown: float
    ) -> None:
        period = next(period for product, _, period in SLOTS if product == feed)
        self.due[feed] += max(1, math.floor((started - self.due[feed]) / period) + 1) * period
        self.available = max(started + self.spacing, finished + cooldown)
        self.failures[feed] = 0 if success else self.failures[feed] + 1
        if not success:
            self.blocked[feed] = finished + min(300, 15 * 2 ** min(self.failures[feed] - 1, 5))

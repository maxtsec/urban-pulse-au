"""Pure fixture projection and age rules, independent of storage and spatial engines."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from urbanpulse.contracts.events import (
    EventReceipt,
    RevisionOutcome,
    VehiclePositionChanged,
    compare_revision,
)

POSITION_STALE_SECONDS = 120
POSITION_EXPIRED_SECONDS = 300
POSITION_FRESHNESS_VERSION = "southbank-position-freshness-v1"


def position_freshness_policy() -> dict[str, str | int]:
    """Versioned fixture thresholds shared with HTTP clients and checkpoints."""
    return {
        "version": POSITION_FRESHNESS_VERSION,
        "stale_after_seconds": POSITION_STALE_SECONDS,
        "expired_after_seconds": POSITION_EXPIRED_SECONDS,
    }


class Freshness(StrEnum):
    CURRENT = "current"
    STALE = "stale"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


def position_freshness(observed_at: datetime | None, at: datetime) -> Freshness:
    if observed_at is None or observed_at > at:
        return Freshness.UNKNOWN
    elapsed = at - observed_at
    age_us = (elapsed.days * 86400 + elapsed.seconds) * 1_000_000 + elapsed.microseconds
    if age_us >= POSITION_EXPIRED_SECONDS * 1_000_000:
        return Freshness.EXPIRED
    if age_us >= POSITION_STALE_SECONDS * 1_000_000:
        return Freshness.STALE
    return Freshness.CURRENT


@dataclass(frozen=True)
class AcceptedPosition:
    event: VehiclePositionChanged
    receipt: EventReceipt


class PositionProjection:
    """One bounded replay; the caller supplies the complete captured fixture history."""

    def __init__(self) -> None:
        self.positions: dict[str, AcceptedPosition] = {}
        self.receipts: dict[tuple[str, str], EventReceipt] = {}
        self.outcomes = {outcome.value: 0 for outcome in RevisionOutcome}

    def consume(self, event: VehiclePositionChanged) -> RevisionOutcome:
        receipt = EventReceipt.from_event(event)
        current = self.positions.get(event.subject)
        outcome = compare_revision(
            receipt,
            current.receipt if current else None,
            prior_receipt=self.receipts.get((event.source, event.id)),
        )
        self.outcomes[outcome.value] += 1
        if outcome == RevisionOutcome.APPLY:
            self.positions[event.subject] = AcceptedPosition(event, receipt)
        if outcome != RevisionOutcome.CONFLICT:
            self.receipts[(event.source, event.id)] = receipt
        return outcome

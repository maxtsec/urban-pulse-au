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


class Freshness(StrEnum):
    CURRENT = "current"
    STALE = "stale"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


def position_freshness(observed_at: datetime | None, at: datetime) -> Freshness:
    if observed_at is None or observed_at > at:
        return Freshness.UNKNOWN
    age = (at - observed_at).total_seconds()
    if age >= 300:
        return Freshness.EXPIRED
    if age >= 120:
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

"""Latest published service/coverage state with per-handler revision receipts."""

from typing import Any

from urbanpulse.contracts.events import CloudEvent, EventReceipt, RevisionOutcome, compare_revision


class PublishedProjection:
    def __init__(self) -> None:
        self.events: dict[tuple[str, str], CloudEvent[Any]] = {}
        self.current: dict[tuple[str, str], EventReceipt] = {}
        self.receipts: dict[tuple[str, str], EventReceipt] = {}

    def consume(self, event: CloudEvent[Any]) -> RevisionOutcome:
        receipt = EventReceipt.from_event(event)
        key = (event.source, event.subject)
        outcome = compare_revision(
            receipt,
            self.current.get(key),
            prior_receipt=self.receipts.get((event.source, event.id)),
        )
        if outcome == RevisionOutcome.APPLY:
            self.events[key] = event
            self.current[key] = receipt
        if outcome != RevisionOutcome.CONFLICT:
            self.receipts[(event.source, event.id)] = receipt
        return outcome

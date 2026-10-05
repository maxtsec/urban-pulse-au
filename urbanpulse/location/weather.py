"""Location-owned weather projection consuming published contracts only."""

from datetime import datetime
from typing import Any, Protocol

from urbanpulse.contracts.events import EventReceipt, RevisionOutcome, compare_revision
from urbanpulse.contracts.weather import (
    LEVELS,
    PRODUCTS,
    ModelledReadingChanged,
    WeatherWarningChanged,
)
from urbanpulse.location.status import AdverseFact

WeatherEvent = WeatherWarningChanged | ModelledReadingChanged


class WarningMembership(Protocol):
    def overlaps(self, area: dict[str, Any], warning: dict[str, Any]) -> bool | None: ...


class WeatherProjection:
    def __init__(self) -> None:
        self.events: dict[tuple[str, str], WeatherEvent] = {}
        self.receipts: dict[tuple[str, str], EventReceipt] = {}
        self.current: dict[tuple[str, str], EventReceipt] = {}
        self.outcomes = {outcome.value: 0 for outcome in RevisionOutcome}

    def consume(self, event: WeatherEvent) -> RevisionOutcome:
        receipt = (
            EventReceipt.from_event(event)
            if isinstance(event, WeatherWarningChanged)
            else EventReceipt.from_event(event)
        )
        key = (event.source, event.subject)
        outcome = compare_revision(
            receipt,
            self.current.get(key),
            prior_receipt=self.receipts.get((event.source, event.id)),
        )
        self.outcomes[outcome.value] += 1
        if outcome == RevisionOutcome.APPLY:
            self.events[key] = event
            self.current[key] = receipt
        if outcome != RevisionOutcome.CONFLICT:
            self.receipts[(event.source, event.id)] = receipt
        return outcome

    def warnings(
        self, at: datetime, area: dict[str, Any], spatial: WarningMembership
    ) -> tuple[list[dict[str, Any]], tuple[AdverseFact, ...], bool]:
        views = []
        facts = []
        complete = True
        for key, event in sorted(self.events.items()):
            if not isinstance(event, WeatherWarningChanged):
                continue
            state, data = event.data.state, event.data
            geometry = state.geometry.model_dump(mode="json") if state.geometry else None
            applicable = spatial.overlaps(area, geometry) if geometry else None
            recognized = (
                data.provenance.provider == "vicemergency"
                and state.level in LEVELS
                and data.provenance.product in PRODUCTS
            )
            lifecycle = (
                "cancelled"
                if state.cancelled_at is not None and state.cancelled_at <= at
                else "expired"
                if data.effective_until is not None and at >= data.effective_until
                else "scheduled"
                if data.effective_from is not None and at < data.effective_from
                else "active"
            )
            if lifecycle in {"active", "scheduled"} and (not recognized or applicable is None):
                complete = False
            if lifecycle == "active" and recognized and applicable and state.level != "Advice":
                assert data.effective_from is not None
                facts.append(
                    AdverseFact(
                        id=f"{event.source}/{event.subject}",
                        input_id="weather_warnings",
                        reason=f"{state.level}: {state.headline}",
                        effective_from=data.effective_from,
                        effective_until=data.effective_until,
                    )
                )
            views.append(
                {
                    **state.model_dump(mode="json"),
                    "id": key[1],
                    "lifecycle": lifecycle,
                    "applicable": applicable,
                    "recognized": recognized,
                    "geometry": geometry if applicable is not None else None,
                    "effective_from": data.effective_from,
                    "effective_until": data.effective_until,
                    "event_id": event.id,
                    "revision": data.revision,
                    "provenance": data.provenance.model_dump(mode="json"),
                }
            )
        return views, tuple(facts), complete

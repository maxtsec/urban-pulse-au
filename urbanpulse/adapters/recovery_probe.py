"""Synthetic database effect for the recovery CLI, not a Location Intelligence projection."""

from urbanpulse.adapters.event_store import PostgresEventTransaction
from urbanpulse.adapters.event_tables import probe_effects
from urbanpulse.application.durable_delivery import (
    DeliveryClaim,
    EventTransaction,
    receipt_from_wire,
)

CONSUMER = "recovery-probe-v1"


def apply_probe(claim: DeliveryClaim, transaction: EventTransaction, wire: str) -> None:
    if not isinstance(transaction, PostgresEventTransaction):
        raise TypeError("probe requires a PostgreSQL transaction binding")
    event = receipt_from_wire(wire)
    transaction.connection.execute(
        probe_effects.insert().values(
            context=claim.context,
            source=event.source,
            event_id=event.event_id,
        )
    )

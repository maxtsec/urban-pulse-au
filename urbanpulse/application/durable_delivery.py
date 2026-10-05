"""Durable publication/receipt ports; enqueue success is not handler completion."""

import re
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from pydantic import TypeAdapter

from urbanpulse.contracts.composition import (
    AreaStatusChanged,
    SourceCoverageChanged,
    TransportServiceStatusChanged,
)
from urbanpulse.contracts.events import EventReceipt, RevisionOutcome, VehiclePositionChanged
from urbanpulse.contracts.planning import PlanningSnapshotPublished
from urbanpulse.contracts.weather import ModelledReadingChanged, WeatherWarningChanged

type IntegrationEvent = (
    VehiclePositionChanged
    | TransportServiceStatusChanged
    | SourceCoverageChanged
    | AreaStatusChanged
    | PlanningSnapshotPublished
    | ModelledReadingChanged
    | WeatherWarningChanged
)
EVENT: TypeAdapter[IntegrationEvent] = TypeAdapter(IntegrationEvent)
MAX_ATTEMPTS = 3


class PublicationConflict(ValueError):
    """An immutable publication identity or consumer set was changed."""


class StorageUnavailable(RuntimeError):
    """The storage transaction could not finish; this is not a handler failure."""


class InvalidPublication(ValueError):
    """Stored wire bytes or receipt metadata cannot be trusted."""


class FailureCategory(StrEnum):
    HANDLER = "handler-error"
    INVALID = "invalid-envelope"
    CONFLICT = "publication-conflict"


class ReplayReason(StrEnum):
    OPERATOR_RETRY = "operator-retry"
    HANDLER_FIXED = "handler-fixed"
    VERIFY_DEDUPLICATION = "verify-deduplication"


def retry_delay(attempt_count: int) -> int:
    return 1 if attempt_count == 1 else 5


class StaleClaim(ValueError):
    """A worker no longer holds the current, unexpired delivery claim."""


class TransactionAborted(ValueError):
    """A failed operation prevents committing any changes in its unit of work."""


def validate_key(value: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}", value):
        raise ValueError("context and consumer keys require 1-200 ASCII identifier characters")


def receipt_from_wire(wire: str) -> EventReceipt:
    event = EVENT.validate_json(wire)
    receipt = EventReceipt.from_event(event)
    if receipt.revision > 2**63 - 1:
        raise ValueError("durable revision exceeds signed 64-bit storage")
    return receipt


@dataclass(frozen=True)
class DeliveryClaim:
    delivery_id: str
    generation: int
    context: str
    consumer: str
    lease_until: datetime


class EventTransaction(Protocol):
    def publish(
        self,
        context: str,
        wire: str,
        consumers: Sequence[str],
        *,
        after: str | None = None,
    ) -> str: ...

    def delivery_state(self, publication_id: str, consumer: str) -> str: ...

    def consume(
        self, context: str, consumer: str, wire: str, effect: Callable[[], None]
    ) -> RevisionOutcome: ...


class EventStore(Protocol):
    def transaction(self) -> AbstractContextManager[EventTransaction]: ...

    def claim(
        self, consumer: str, *, limit: int = 1, lease_seconds: float = 30
    ) -> tuple[DeliveryClaim, ...]: ...

    def complete(
        self, claim: DeliveryClaim, effect: Callable[[EventTransaction, str], None]
    ) -> RevisionOutcome: ...


class RecoveryStore(EventStore, Protocol):
    def release_infrastructure(self, claim: DeliveryClaim) -> str: ...

    def fail(self, claim: DeliveryClaim, category: FailureCategory) -> str: ...

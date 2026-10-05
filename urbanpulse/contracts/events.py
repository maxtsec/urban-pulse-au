"""CloudEvents 1.0 profile and a pure per-aggregate revision guard."""

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)


def require_timestamp(value: object) -> object:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}"
        r"(?:\.[0-9]+)?(?:[Zz]|[+-][0-9]{2}:[0-9]{2})",
        value,
    ):
        raise ValueError("wire timestamps must use RFC 3339 with a timezone")
    return value


Timestamp = Annotated[
    AwareDatetime,
    BeforeValidator(require_timestamp),
    AfterValidator(lambda value: value.astimezone(UTC)),
]


def require_finite_numbers(value: object) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("optional fields must contain only finite numbers")
    if isinstance(value, dict):
        for item in value.values():
            require_finite_numbers(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            require_finite_numbers(item)


def normalize_unicode_string(value: str) -> str:
    try:
        return value.encode("utf-16-le", errors="surrogatepass").decode("utf-16-le")
    except UnicodeError as error:
        raise ValueError("CloudEvents wire strings cannot contain unpaired surrogates") from error


def normalize_context_string(value: str) -> str:
    normalized = normalize_unicode_string(value)
    for char in normalized:
        code = ord(char)
        if code <= 0x1F or 0x7F <= code <= 0x9F or 0xFDD0 <= code <= 0xFDEF:
            raise ValueError("CloudEvents strings cannot contain controls or noncharacters")
        if code & 0xFFFF in (0xFFFE, 0xFFFF):
            raise ValueError("CloudEvents strings cannot contain noncharacters")
    return normalized


Identifier = Annotated[
    str,
    StringConstraints(min_length=1, pattern=r"^\S+$"),
    AfterValidator(normalize_context_string),
]


def normalize_wire_strings(value: object) -> object:
    """Reject malformed Unicode before a Python-created payload can be accepted."""
    if isinstance(value, str):
        return normalize_unicode_string(value)
    if isinstance(value, dict):
        normalized: dict[object, object] = {}
        for key, item in value.items():
            normalized_key = normalize_unicode_string(key) if isinstance(key, str) else key
            if normalized_key in normalized:
                raise ValueError("wire keys must be unique after Unicode normalization")
            normalized[normalized_key] = normalize_wire_strings(item)
        return normalized
    if isinstance(value, list):
        return [normalize_wire_strings(item) for item in value]
    if isinstance(value, tuple):
        return tuple(normalize_wire_strings(item) for item in value)
    return value


def normalize_numbers(value: object) -> object:
    """Give equal JSON numbers one fingerprint without converting integers to floats."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {key: normalize_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_numbers(item) for item in value]
    return value


class WireModel(BaseModel):
    """Preserve optional additions when reading and forwarding a v1 payload."""

    model_config = ConfigDict(extra="allow", frozen=True, allow_inf_nan=False)

    @model_validator(mode="before")
    @classmethod
    def valid_wire_strings(cls, value: object) -> object:
        return normalize_wire_strings(value)

    @model_validator(mode="after")
    def finite_extras(self) -> Self:
        require_finite_numbers(self.model_extra)
        return self


class Provenance(WireModel):
    provider: Identifier
    product: Identifier
    record_id: Identifier
    capture_ids: tuple[Identifier, ...]
    source_observed_at: Timestamp | None

    @model_validator(mode="after")
    def unique_captures(self) -> Self:
        if len(set(self.capture_ids)) != len(self.capture_ids):
            raise ValueError("capture_ids must be unique")
        return self


class Position(WireModel):
    longitude: float = Field(strict=True, ge=-180, le=180)
    latitude: float = Field(strict=True, ge=-90, le=90)


class VehiclePosition(WireModel):
    vehicle_id: Identifier
    route_id: Identifier | None
    position: Position
    observed_at: Timestamp | None


class EventData[Payload: WireModel](WireModel):
    schema_version: str = Field(pattern=r"^1\.[0-9]+$")
    revision: int = Field(strict=True, ge=1)
    provenance: Provenance
    effective_from: Timestamp | None
    effective_until: Timestamp | None
    correlation_id: Identifier
    causation_id: Identifier | None
    state: Payload

    @model_validator(mode="after")
    def valid_interval(self) -> "EventData[Payload]":
        if (
            self.effective_from is not None
            and self.effective_until is not None
            and self.effective_until <= self.effective_from
        ):
            raise ValueError("effective_until must be after effective_from")
        return self


class CloudEvent[Payload: WireModel](WireModel):
    specversion: Literal["1.0"]
    id: Identifier
    source: str = Field(pattern=r"^urn:urbanpulse:(fixture|live):[a-z][a-z0-9-]*$")
    type: str = Field(pattern=r"^au\.urbanpulse\.[a-z-]+\.[a-z-]+\.v1$")
    subject: Identifier
    time: Timestamp
    datacontenttype: Literal["application/json"]
    upmode: Literal["fixture", "live"]
    data: EventData[Payload]

    @model_validator(mode="before")
    @classmethod
    def normalize_extensions(cls, value: object) -> object:
        if isinstance(value, dict):
            return {
                name: (
                    normalize_context_string(item)
                    if name not in cls.model_fields and isinstance(item, str)
                    else item
                )
                for name, item in value.items()
                if name in cls.model_fields or item is not None
            }
        return value

    @model_validator(mode="after")
    def consistent_mode(self) -> "CloudEvent[Payload]":
        if self.source.split(":")[2] != self.upmode:
            raise ValueError("source namespace must match upmode")
        for name, value in (self.model_extra or {}).items():
            if not name.isascii() or not name.isalnum() or name != name.lower():
                raise ValueError("CloudEvents extension names use lowercase ASCII letters/digits")
            if type(value) not in (str, int, bool):
                raise ValueError("CloudEvents extensions must be JSON string, integer or boolean")
            if type(value) is int and not -(2**31) <= value < 2**31:
                raise ValueError("CloudEvents extension integers must fit signed 32 bits")
        return self


class VehiclePositionChanged(CloudEvent[VehiclePosition]):
    type: Literal["au.urbanpulse.transport.vehicle-position-changed.v1"]

    @model_validator(mode="after")
    def consistent_position(self) -> "VehiclePositionChanged":
        if not self.source.endswith(":transport"):
            raise ValueError("position events must be owned by transport")
        if self.subject != self.data.state.vehicle_id:
            raise ValueError("subject must match the source-scoped vehicle_id")
        if not self.data.provenance.capture_ids:
            raise ValueError("a position event requires capture provenance")
        if self.data.state.observed_at != self.data.provenance.source_observed_at:
            raise ValueError("position and provenance observation times must agree")
        if self.data.effective_until is not None:
            raise ValueError("position effective_until must be null; freshness is consumer policy")
        if self.data.effective_from != self.data.state.observed_at:
            raise ValueError("position effective_from must equal observed_at, including null")
        return self


@dataclass(frozen=True)
class EventReceipt:
    """Accepted metadata only; storage and transactional application are separate."""

    source: str
    subject: str
    event_id: str
    revision: int
    fingerprint: str

    @classmethod
    def from_event(cls, event: CloudEvent[Any]) -> "EventReceipt":
        serialized = json.dumps(
            # Delivery tracing can change without changing the published event.
            normalize_numbers(event.model_dump(mode="json", exclude={"traceparent", "tracestate"})),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return cls(
            source=event.source,
            subject=event.subject,
            event_id=event.id,
            revision=event.data.revision,
            fingerprint=hashlib.sha256(serialized).hexdigest(),
        )


class RevisionOutcome(StrEnum):
    APPLY = "apply"
    DUPLICATE = "duplicate"
    SUPERSEDED = "superseded"
    CONFLICT = "conflict"


def compare_revision(
    incoming: EventReceipt,
    current: EventReceipt | None,
    *,
    prior_receipt: EventReceipt | None = None,
) -> RevisionOutcome:
    """Check a source/event-ID receipt lookup before the aggregate ordering cursor."""
    if prior_receipt is not None:
        if (incoming.source, incoming.event_id) != (prior_receipt.source, prior_receipt.event_id):
            raise ValueError("prior receipt must match the incoming source/event ID")
        if incoming == prior_receipt:
            return RevisionOutcome.DUPLICATE
        return RevisionOutcome.CONFLICT
    if current is None:
        return RevisionOutcome.APPLY
    if (incoming.source, incoming.subject) != (current.source, current.subject):
        raise ValueError("cannot compare different producer/aggregate scopes")
    if incoming.event_id == current.event_id:
        if incoming.fingerprint == current.fingerprint and incoming.revision == current.revision:
            return RevisionOutcome.DUPLICATE
        return RevisionOutcome.CONFLICT
    if incoming.revision == current.revision:
        return RevisionOutcome.CONFLICT
    if incoming.revision < current.revision:
        return RevisionOutcome.SUPERSEDED
    return RevisionOutcome.APPLY

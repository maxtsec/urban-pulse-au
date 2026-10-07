"""Versioned local capture records; raw receipt is distinct from source validity."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

TramFeed = Literal["vehicle-positions", "trip-updates", "service-alerts"]
FEEDS: tuple[TramFeed, ...] = ("vehicle-positions", "trip-updates", "service-alerts")
MAX_BYTES = 8 * 1024 * 1024
Mode = Literal["fixture", "live"]
Failure = Literal["http_error", "encoding", "size_limit", "time_limit", "network_error"]


@dataclass(frozen=True)
class FetchResult:
    requested_at: datetime
    received_at: datetime
    http_status: int | None
    payload: bytes | None = field(repr=False)
    reason: Failure | None = None
    retry_after_seconds: float | None = None
    content_type: str | None = None
    content_encoding: Literal["identity"] = "identity"


class Source(Protocol):
    def fetch(self, feed: TramFeed) -> FetchResult: ...


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["capture-v1"] = "capture-v1"


class Intent(Record):
    capture_id: UUID
    mode: Mode
    provider: Literal["transport-victoria", "synthetic"]
    product: TramFeed
    requested_at: AwareDatetime
    collector_version: str = Field(min_length=1, max_length=100)


class Receipt(Record):
    capture_id: UUID
    requested_at: AwareDatetime
    received_at: AwareDatetime
    http_status: Literal[200] = 200
    content_type: str | None = Field(default=None, max_length=128)
    content_encoding: Literal["identity"] = "identity"
    byte_length: int = Field(ge=0, le=MAX_BYTES)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload_locator: Literal["response/payload.bin"] = "response/payload.bin"
    source_observed_at: None = None
    source_time_reason: Literal["not-yet-decoded"] = "not-yet-decoded"


class Manifest(Record):
    capture_id: UUID
    outcome: Literal["captured", "fetch-failed", "raw-write-failed", "abandoned"]
    completed_at: AwareDatetime
    reason: Failure | Literal["storage_error", "interrupted"] | None = None
    http_status: int | None = Field(default=None, ge=100, le=599)
    receipt: Receipt | None = None
    retry_not_before: AwareDatetime | None = None

    @model_validator(mode="after")
    def consistent_outcome(self) -> Self:
        if self.outcome == "captured":
            if self.receipt is None or self.reason is not None or self.http_status != 200:
                raise ValueError("captured_requires_receipt")
        elif self.receipt is not None or self.reason is None:
            raise ValueError("failure_requires_reason_without_receipt")
        if self.outcome == "abandoned" and (
            self.reason != "interrupted" or self.http_status is not None
        ):
            raise ValueError("invalid_abandoned_outcome")
        if self.outcome == "raw-write-failed" and self.reason != "storage_error":
            raise ValueError("invalid_storage_failure")
        if self.outcome == "fetch-failed" and self.reason not in {
            "http_error",
            "encoding",
            "size_limit",
            "time_limit",
            "network_error",
        }:
            raise ValueError("invalid_fetch_failure")
        return self


class CaptureError(RuntimeError):
    """Only fixed safe messages cross the CLI boundary."""


class Journal(Protocol):
    def begin(self, mode: Mode, feed: TramFeed, version: str) -> Intent: ...
    def complete(self, intent: Intent, result: FetchResult) -> Manifest: ...

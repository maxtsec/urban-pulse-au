"""Bounded capture control state; immutable evidence remains in the journal."""

import hashlib
import json
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from urbanpulse.contracts.local_capture import FEEDS, Intent, Manifest

MAX_SEQUENCE = 2**63 - 1
OUTCOMES = ("captured", "fetch-failed", "raw-write-failed", "abandoned")


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


class Summary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    outcomes: dict[str, Annotated[int, Field(strict=True, ge=0)]] = Field(
        default_factory=lambda: dict.fromkeys(OUTCOMES, 0)
    )
    last_capture_at: dict[str, AwareDatetime] = Field(default_factory=dict)
    retry_not_before: AwareDatetime | None = None

    @model_validator(mode="after")
    def bounded_keys(self) -> Self:
        if set(self.outcomes) != set(OUTCOMES) or any(
            type(n) is not int or n < 0 for n in self.outcomes.values()
        ):
            raise ValueError("invalid_counts")
        if not set(self.last_capture_at) <= {
            mode + "/" + feed for mode in ("fixture", "live") for feed in FEEDS
        }:
            raise ValueError("invalid_feed_summary")
        return self

    def include(self, intent: Intent, manifest: Manifest) -> "Summary":
        values = self.model_dump()
        values["outcomes"][manifest.outcome] += 1
        if manifest.receipt is not None:
            key = intent.mode + "/" + intent.product
            received = manifest.receipt.received_at
            values["last_capture_at"][key] = max(self.last_capture_at.get(key, received), received)
        if intent.mode == "live" and manifest.retry_not_before is not None:
            values["retry_not_before"] = max(
                self.retry_not_before or manifest.retry_not_before, manifest.retry_not_before
            )
        return Summary.model_validate(values)


class Control(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["capture-control-v1"] = "capture-control-v1"
    store_id: UUID
    generation: int = Field(default=0, ge=0, strict=True)
    next_capture_sequence: int = Field(default=1, ge=1, le=MAX_SEQUENCE, strict=True)
    pending: Intent | None = None
    summary: Summary = Field(default_factory=Summary)

    @model_validator(mode="after")
    def consistent_accounting(self) -> Self:
        allocated = self.next_capture_sequence - 1
        complete = sum(self.summary.outcomes.values())
        if complete + int(self.pending is not None) != allocated:
            raise ValueError("invalid_sequence_accounting")
        if self.generation != 2 * complete + int(self.pending is not None):
            raise ValueError("invalid_generation")
        if self.pending is not None and self.pending.capture_sequence != allocated:
            raise ValueError("invalid_pending_sequence")
        return self

    def document(self) -> dict[str, object]:
        body = self.model_dump(mode="json")
        return {**body, "checksum": hashlib.sha256(canonical(body)).hexdigest()}

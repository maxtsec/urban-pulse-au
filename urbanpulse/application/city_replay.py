"""Internal fixture timeline; not a live TransportStatusChanged wire contract."""

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from urbanpulse.application.scenarios import ScenarioPolicy
from urbanpulse.contracts.events import Identifier
from urbanpulse.location.status import AdverseFact


class ServiceFrame(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: Identifier
    at_seconds: int = Field(strict=True, ge=0)
    capture_ids: tuple[Identifier, ...] = Field(min_length=1)
    stop_id: Identifier
    status: Literal["clear", "disrupted"]
    reason: str = Field(min_length=1)


def received(frame_seconds: int, seconds: int, policy: ScenarioPolicy, outage_at: int) -> bool:
    return (
        not policy.transport_empty
        and frame_seconds <= seconds
        and (not policy.transport_outage or frame_seconds < outage_at)
    )


def service_at(
    frames: tuple[ServiceFrame, ...],
    started_at: datetime,
    seconds: int,
    policy: ScenarioPolicy,
    outage_at: int,
) -> tuple[AdverseFact | None, dict[str, Any] | None]:
    fact: AdverseFact | None = None
    evidence: dict[str, Any] | None = None
    for frame in frames:
        if not received(frame.at_seconds, seconds, policy, outage_at):
            continue
        observed_at = started_at + timedelta(seconds=frame.at_seconds)
        evidence = {
            "event_id": frame.id,
            "capture_ids": frame.capture_ids,
            "observed_at": observed_at,
            "stop_id": frame.stop_id,
            "status": frame.status,
        }
        if frame.status == "clear":
            fact = None
        elif fact is None:
            # One episode starts at its first observed interruption; frame IDs are revisions.
            fact = AdverseFact(
                id=frame.id,
                input_id="transport_service",
                reason=frame.reason,
                effective_from=observed_at,
            )
        else:
            fact = replace(fact, reason=frame.reason)
    return fact, evidence

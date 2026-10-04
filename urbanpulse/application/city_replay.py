"""Internal fixture timeline; not a live TransportStatusChanged wire contract."""

from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

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


def received(frame_seconds: int, seconds: int, scenario: str, outage_at: int) -> bool:
    return (
        scenario != "empty"
        and frame_seconds <= seconds
        and (scenario != "outage" or frame_seconds < outage_at)
    )


def service_at(
    frames: tuple[ServiceFrame, ...],
    started_at: datetime,
    seconds: int,
    scenario: str,
    outage_at: int,
) -> tuple[AdverseFact | None, dict[str, Any] | None]:
    latest = next(
        (
            frame
            for frame in reversed(frames)
            if received(frame.at_seconds, seconds, scenario, outage_at)
        ),
        None,
    )
    if latest is None:
        return None, None
    observed_at = started_at + timedelta(seconds=latest.at_seconds)
    evidence = {
        "event_id": latest.id,
        "capture_ids": latest.capture_ids,
        "observed_at": observed_at,
        "stop_id": latest.stop_id,
        "status": latest.status,
    }
    fact = (
        AdverseFact(
            id=latest.id,
            input_id="transport_service",
            reason=latest.reason,
            effective_from=observed_at,
        )
        if latest.status == "disrupted"
        else None
    )
    return fact, evidence

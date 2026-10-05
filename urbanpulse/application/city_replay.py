"""Fixture frame validation and scenario-policy receipt cutoffs."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from urbanpulse.application.scenarios import ScenarioPolicy
from urbanpulse.contracts.events import Identifier


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

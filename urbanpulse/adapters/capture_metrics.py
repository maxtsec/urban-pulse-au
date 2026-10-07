"""Projection of local capture observations onto the accepted raw-only metrics."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from urbanpulse.contracts.local_capture import FEEDS

PREFIX = "custom.googleapis.com/urbanpulse/collector/v1/"
Counter = Annotated[int, Field(strict=True, ge=0, le=2**63 - 1)]


class MonitoringTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    project: str = Field(pattern=r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
    collector: str = Field(pattern=r"^[a-z][a-z0-9-]{0,62}$")

    def resource(self) -> dict[str, object]:
        return {
            "type": "generic_task",
            "labels": {
                "project_id": self.project,
                "location": "australia-southeast2",
                "namespace": "urbanpulse",
                "job": "capture",
                "task_id": self.collector,
            },
        }


class Pulse(BaseModel):
    # Session IDs/outcomes are deliberately not forwarded as labels or claims.
    model_config = ConfigDict(extra="ignore")
    kind: Literal["collector_heartbeat_dry_run"]
    mode: Literal["live", "fixture"]
    state: str = Field(max_length=80)
    emitted_at: AwareDatetime
    last_capture_at: dict[str, AwareDatetime]
    free_bytes: Counter
    free_inodes: Counter

    @model_validator(mode="after")
    def bounded_summary(self) -> "Pulse":
        if not set(self.last_capture_at) <= {"live/" + feed for feed in FEEDS}:
            raise ValueError("invalid_live_summary")
        return self


def raw_series(pulse: Pulse, target: MonitoringTarget) -> list[dict[str, object]]:
    """No fixture data, upload claims, invented success or future capture ages."""
    if pulse.mode != "live":
        raise ValueError("live_pulse_required")
    if any(stamp > pulse.emitted_at for stamp in pulse.last_capture_at.values()):
        raise ValueError("capture_clock_in_future")
    at = pulse.emitted_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    result: list[dict[str, object]] = []

    def add(name: str, value: int, feed: str | None = None) -> None:
        result.append(
            {
                "metric": {"type": PREFIX + name, "labels": {"feed": feed} if feed else {}},
                "resource": target.resource(),
                "metricKind": "GAUGE",
                "valueType": "INT64",
                "points": [{"interval": {"endTime": at}, "value": {"int64Value": str(value)}}],
            }
        )

    # A final/error record must not prolong the healthy-loop heartbeat series.
    if pulse.state == "running":
        add("heartbeat", 1)
    add("free_bytes", pulse.free_bytes)
    add("free_inodes", pulse.free_inodes)
    for feed in FEEDS:
        captured = pulse.last_capture_at.get("live/" + feed)
        add("capture_success_known", int(captured is not None), feed)
        if captured is not None:
            age = pulse.emitted_at - captured
            add("capture_age_seconds", age.days * 86400 + age.seconds, feed)
    return result


def current_pulse(pulse: Pulse, now: datetime, previous: datetime | None) -> None:
    if not 0 <= (now - pulse.emitted_at).total_seconds() <= 5:
        raise ValueError("pulse_clock_invalid")
    if previous is not None and pulse.emitted_at <= previous:
        raise ValueError("pulse_clock_regressed")

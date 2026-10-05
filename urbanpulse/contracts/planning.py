"""Published planning snapshots; source status is profile context, not a condition."""

from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from urbanpulse.contracts.events import CloudEvent, Identifier, Position, Timestamp, WireModel

PLANNING_SCOPE = "city-of-melbourne/development-activity-monitor/synthetic-pilot"
SOURCE_URL = "https://data.melbourne.vic.gov.au/explore/dataset/development-activity-monitor/"


class PlanningRecord(WireModel):
    development_key: Identifier
    name: str = Field(min_length=1)
    status: str = Field(min_length=1)
    clue_small_area: str | None
    position: Position | None
    year_completed: int | None = Field(default=None, strict=True, ge=1900, le=2200)


class PlanningSnapshot(WireModel):
    scope_id: Literal["city-of-melbourne/development-activity-monitor/synthetic-pilot"]
    snapshot_id: Identifier
    as_of: Timestamp | None
    complete: Literal[True]
    records: tuple[PlanningRecord, ...] = Field(max_length=1000)

    @field_validator("records")
    @classmethod
    def unique_sorted_records(
        cls, records: tuple[PlanningRecord, ...]
    ) -> tuple[PlanningRecord, ...]:
        if len({record.development_key for record in records}) != len(records):
            raise ValueError("snapshot development keys must be unique")
        return tuple(sorted(records, key=lambda record: record.development_key))


class PlanningSnapshotPublished(CloudEvent[PlanningSnapshot]):
    type: Literal["au.urbanpulse.planning.snapshot-published.v1"]

    @model_validator(mode="after")
    def consistent_snapshot(self) -> Self:
        provenance = self.data.provenance
        if (
            self.subject != self.data.state.scope_id
            or self.subject != f"{provenance.provider}/{provenance.product}/{provenance.record_id}"
            or self.source != "urn:urbanpulse:fixture:planning"
            or self.upmode != "fixture"
        ):
            raise ValueError("planning fixture owner and scope identity must agree")
        if not provenance.capture_ids or provenance.source_observed_at != self.data.state.as_of:
            raise ValueError("planning snapshot provenance must preserve capture and source time")
        if self.data.state.as_of is not None and self.data.state.as_of > self.time:
            raise ValueError("snapshot source date cannot follow receipt")
        if self.data.effective_from is not None or self.data.effective_until is not None:
            raise ValueError("planning snapshots do not establish record change or validity times")
        return self

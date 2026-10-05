"""Compose the slower planning profile separately from current-condition facts."""

from datetime import datetime
from typing import Any

from urbanpulse.application.planning_replay import PlanningNormalizer, planning_steps
from urbanpulse.contracts.events import RevisionOutcome
from urbanpulse.contracts.planning import SOURCE_URL
from urbanpulse.location.planning import PlanningMembership, PlanningProjection


def replay_planning(
    bundle: dict[str, Any],
    seconds: int,
    at: datetime,
    outage: bool,
    area: dict[str, Any],
    spatial: PlanningMembership,
    normalizer: PlanningNormalizer,
) -> dict[str, Any]:
    projection = PlanningProjection()
    state = "unknown"
    last_received = None
    rejected = 0
    incomplete = 0
    evidence = []
    for step in planning_steps(bundle, seconds, at, outage, normalizer):
        frame = step.frame
        evidence.append(step.evidence)
        if frame["kind"] == "coverage":
            state = frame["state"]
            continue
        if frame["kind"] in {"rejected", "incomplete"}:
            rejected += frame["kind"] == "rejected"
            incomplete += frame["kind"] == "incomplete"
            state = "unknown"
            continue
        assert step.event is not None
        outcome = None if step.recapture else projection.consume(step.event)
        if frame["kind"] == "redelivery":
            continue
        if outcome not in {None, RevisionOutcome.APPLY, RevisionOutcome.DUPLICATE} or (
            projection.latest is None or projection.latest.id != step.event.id
        ):
            state = "unknown"
            continue
        last_received = frame["received_at"]
        state = "current"
    if outage and seconds >= bundle["outage_at_seconds"]:
        state = "error"
    capture_state = state
    profile = projection.profile(area, spatial)
    latest = projection.latest
    if state == "current" and (
        profile["unlocated_records"] or latest is None or latest.data.state.as_of is None
    ):
        state = "unknown"
    return {
        "mode": "fixture",
        "state": state,
        "capture_state": capture_state,
        "as_of": latest.data.state.as_of if latest else None,
        "snapshot_id": latest.data.state.snapshot_id if latest else None,
        "last_successful_received_at": last_received,
        "description": "Synthetic major development records; area profile only",
        "scope": "Synthetic DAM pilot sample; not all developments or current roadworks",
        "spatial_policy": "southbank-covers-point-no-buffer-v1",
        "coverage_policy": "authored-planning-checkpoints-v1",
        "attribution": {
            "owner": "City of Melbourne",
            "source_url": SOURCE_URL,
            "licence_url": "https://creativecommons.org/licenses/by/4.0/",
            "modifications": "Synthetic records modelled on DAM fields; no real development claims",
        },
        **profile,
        "projection": {**projection.outcomes, "rejected": rejected},
        "incomplete_captures": incomplete,
        "evidence": evidence,
    }

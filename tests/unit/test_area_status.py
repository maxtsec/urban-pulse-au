from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from urbanpulse.location.status import (
    AdverseFact,
    Condition,
    Coverage,
    CoverageState,
    assess_area,
)

NOW = datetime(2026, 10, 4, tzinfo=UTC)
REQUIRED = frozenset({"transport_service", "weather_warnings"})
CURRENT = (
    Coverage("transport_service", CoverageState.CURRENT),
    Coverage("weather_warnings", CoverageState.CURRENT),
)
DISRUPTION = AdverseFact("tram-1", "transport_service", "Service suspended", NOW)
WARNING = AdverseFact(
    "warning-1", "weather_warnings", "Severe weather", NOW, NOW + timedelta(minutes=1)
)


def assess(facts=(), coverage=CURRENT, at=NOW):
    return assess_area(facts=facts, coverage=coverage, required_inputs=REQUIRED, at=at)


def test_known_disruption_with_missing_weather_is_degraded_and_incomplete():
    result = assess((DISRUPTION,), (CURRENT[0],))
    assert result.condition == Condition.DEGRADED
    assert result.incomplete_inputs == ("weather_warnings",)
    assert result.reasons == (DISRUPTION,)


@pytest.mark.parametrize("state", list(CoverageState))
def test_normal_requires_current_complete_inputs(state):
    result = assess(coverage=(CURRENT[0], Coverage("weather_warnings", state)))
    expected = Condition.NORMAL if state == CoverageState.CURRENT else Condition.UNKNOWN
    assert result.condition == expected


def test_empty_or_absent_coverage_cannot_claim_normal():
    assert assess(coverage=()).condition == Condition.UNKNOWN
    assert assess(coverage=(CURRENT[0],)).condition == Condition.UNKNOWN


def test_planning_profile_does_not_change_current_conditions():
    result = assess(coverage=(*CURRENT, Coverage("planning", CoverageState.UNKNOWN)))
    assert result.condition == Condition.NORMAL
    assert Coverage("planning", CoverageState.UNKNOWN) in result.coverage


def test_expiry_without_new_event_removes_only_the_warning():
    before = assess((DISRUPTION, WARNING), at=NOW + timedelta(seconds=59))
    after = assess((DISRUPTION, WARNING), at=NOW + timedelta(seconds=60))
    assert len(before.reasons) == 2
    assert after.condition == Condition.DEGRADED
    assert after.reasons == (DISRUPTION,)


def test_source_failure_does_not_resolve_a_known_unexpired_warning():
    missing = (CURRENT[0], Coverage("weather_warnings", CoverageState.ERROR))
    result = assess((WARNING,), missing)
    assert result.condition == Condition.DEGRADED
    assert result.incomplete_inputs == ("weather_warnings",)
    expired = assess((WARNING,), missing, NOW + timedelta(minutes=1))
    assert expired.condition == Condition.UNKNOWN
    assert expired.reasons == ()


def test_explicit_resolution_and_future_effective_time():
    future = replace(DISRUPTION, effective_from=NOW + timedelta(minutes=1))
    resolved = replace(DISRUPTION, resolved_at=NOW)
    assert assess((future,)).condition == Condition.NORMAL
    assert assess((resolved,)).condition == Condition.NORMAL
    assert assess((future,), at=NOW + timedelta(minutes=1)).condition == Condition.DEGRADED


def test_naive_clocks_and_invalid_intervals_are_rejected():
    with pytest.raises(ValueError, match="timezone"):
        assess(at=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="effective_until"):
        replace(WARNING, effective_until=NOW)


def test_conflicting_inputs_and_empty_policy_are_rejected():
    with pytest.raises(ValueError, match="coverage input IDs"):
        assess(coverage=(CURRENT[0], CURRENT[0]))
    with pytest.raises(ValueError, match="fact IDs"):
        assess((DISRUPTION, DISRUPTION))
    with pytest.raises(ValueError, match="explicit source coverage"):
        assess((WARNING,), coverage=(CURRENT[0],))
    with pytest.raises(ValueError, match="nonempty input policy"):
        assess_area(facts=(), coverage=(), required_inputs=frozenset(), at=NOW)


@pytest.mark.parametrize("input_id", ["planning", "vehicle_positions"])
def test_facts_outside_current_condition_policy_are_rejected(input_id):
    profile_fact = AdverseFact("profile-1", input_id, "Profile change", NOW)
    coverage = (*CURRENT, Coverage(input_id, CoverageState.CURRENT))
    with pytest.raises(ValueError, match="required current-condition inputs"):
        assess((DISRUPTION, profile_fact), coverage)


def test_input_permutations_produce_equal_area_assessments():
    from itertools import permutations

    coverage = (*CURRENT, Coverage("planning", CoverageState.UNKNOWN))
    expected = assess((DISRUPTION, WARNING), coverage)
    for entries in permutations(coverage):
        assert assess((WARNING, DISRUPTION), entries) == expected
    assert tuple(entry.input_id for entry in expected.coverage) == (
        "planning",
        "transport_service",
        "weather_warnings",
    )


def test_resolution_before_effective_start_is_rejected():
    with pytest.raises(ValueError, match="resolved_at must not precede"):
        replace(DISRUPTION, resolved_at=NOW - timedelta(seconds=1))


def test_resolution_boundary_is_exclusive_and_can_equal_effective_start():
    resolved = replace(DISRUPTION, resolved_at=NOW + timedelta(seconds=1))
    assert resolved.active_at(NOW)
    assert not resolved.active_at(NOW + timedelta(seconds=1))
    assert not replace(DISRUPTION, resolved_at=NOW).active_at(NOW)

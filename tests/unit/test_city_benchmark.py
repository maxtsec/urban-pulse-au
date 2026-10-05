"""Benchmark histories must be valid, reproducible and fully consumed."""

from copy import deepcopy
from datetime import datetime, timedelta

import pytest

from scripts.benchmark_city import fingerprint, measure, profile_copies
from scripts.benchmark_workload import planning_history
from urbanpulse.adapters.city_fixture import LocalCityCapture, capture_city
from urbanpulse.adapters.planning_fixture import FixturePlanningNormalizer
from urbanpulse.application.delivery import ProjectionHandler
from urbanpulse.application.planning_replay import planning_steps
from urbanpulse.contracts.events import RevisionOutcome
from urbanpulse.contracts.planning import PlanningSnapshotPublished
from urbanpulse.location.planning import PlanningProjection


@pytest.fixture
def base(tmp_path):
    return LocalCityCapture(tmp_path, capture_city(tmp_path)).read()


@pytest.mark.parametrize("snapshots,records", [(1, 1), (10, 10), (60, 1), (1, 1000)])
def test_history_is_deterministic_accepted_and_preserves_base(base, snapshots, records):
    before = deepcopy(base)
    captured = planning_history(base, snapshots, records)
    assert captured == planning_history(base, snapshots, records)
    assert base == before
    assert captured.capture_id != base.capture_id
    started = datetime.fromisoformat(base.scenario["started_at"])
    steps = tuple(
        planning_steps(
            captured.planning,
            360,
            started + timedelta(seconds=360),
            False,
            FixturePlanningNormalizer(),
        )
    )
    assert len(steps) == snapshots
    projection = PlanningProjection()
    for step in steps:
        assert step.event is not None
        assert step.event.time <= started + timedelta(seconds=step.frame["at_seconds"])
        assert len(step.event.data.state.records) == records
        assert projection.consume(step.event) == RevisionOutcome.APPLY
    assert len(projection.history) == snapshots
    assert len(projection.latest.data.state.records) == records
    assert len({step.frame["at_seconds"] for step in steps}) == snapshots


@pytest.mark.parametrize("snapshots,records", [(0, 1), (61, 1), (1, 0), (1, 1001)])
def test_bounds_reject_invalid_workload(base, snapshots, records):
    with pytest.raises(ValueError):
        planning_history(base, snapshots, records)


def test_measure_rejects_changed_results_and_invalid_repetitions():
    values = iter([{"count": 1}, {"count": 2}])
    with pytest.raises(ValueError, match="changed"):
        measure(lambda: next(values), 1)
    with pytest.raises(ValueError, match="repetition"):
        measure(lambda: None, 0)
    result = measure(lambda: {"count": 1}, 2)
    assert len(result["samples_ms"]) == 2
    assert result["result_sha256"] == fingerprint({"count": 1})


def test_copy_instrumentation_restores_handler_and_preserves_results(base):
    captured = planning_history(base, 3, 2)
    started = datetime.fromisoformat(base.scenario["started_at"])
    steps = tuple(
        planning_steps(
            captured.planning,
            360,
            started + timedelta(seconds=360),
            False,
            FixturePlanningNormalizer(),
        )
    )

    def replay():
        handler = ProjectionHandler(
            "planning",
            PlanningProjection(),
            PlanningSnapshotPublished.model_validate_json,
            PlanningProjection.consume,
        )
        for step in steps:
            handler.handle(step.event.model_dump_json())
        return [event.id for event in handler.state.history]

    from urbanpulse.application import delivery

    original = delivery.deepcopy
    profile = profile_copies(replay, fingerprint(replay()))
    assert profile["planning_calls"] == 3
    assert profile["calls"] == 3
    assert delivery.deepcopy is original
    with pytest.raises(ValueError, match="differs"):
        profile_copies(replay, "wrong")
    assert delivery.deepcopy is original

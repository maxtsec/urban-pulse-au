"""Durable timer planning respects the bounded fixture clock and domain age policy."""

from datetime import datetime

import pytest
from test_composition import inputs as inputs

from urbanpulse.application.city_checkpoints import clocks
from urbanpulse.contracts.events import VehiclePositionChanged
from urbanpulse.location.city import POSITION_EXPIRED_SECONDS, POSITION_STALE_SECONDS


@pytest.mark.parametrize("target", [-1, 361, True, 1.5, "60", None])
def test_invalid_durable_clock_is_rejected(inputs, target):
    with pytest.raises(ValueError, match="fixture clock"):
        clocks(inputs, target)


def test_plans_position_freshness_and_warning_expiry_without_future_work(inputs):
    actual = clocks(inputs, 360)
    assert actual == sorted(set(actual))
    assert actual[0] == 0 and actual[-1] == 360
    started = datetime.fromisoformat(inputs.captured.scenario["started_at"])
    event = VehiclePositionChanged.model_validate(inputs.captured.scenario["frames"][0]["event"])
    observed = int((event.data.state.observed_at - started).total_seconds())
    assert observed + POSITION_STALE_SECONDS in actual
    assert observed + POSITION_EXPIRED_SECONDS in actual
    assert 240 in actual  # Received warning expires without a replacement capture.
    assert clocks(inputs, 239)[-1] == 239
    assert all(value <= 239 for value in clocks(inputs, 239))

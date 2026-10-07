import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from urbanpulse.location.city import (
    POSITION_EXPIRED_SECONDS,
    POSITION_STALE_SECONDS,
    position_freshness,
    position_freshness_policy,
)


@pytest.mark.parametrize("threshold,state", [(120, "stale"), (300, "expired")])
def test_exact_microsecond_thresholds(threshold, state):
    observation = datetime(2026, 10, 7, microsecond=400, tzinfo=UTC)
    exact = observation + timedelta(seconds=threshold)
    assert position_freshness(observation, exact) == state
    assert position_freshness(observation, exact - timedelta(microseconds=1)) != state
    assert position_freshness(observation, exact + timedelta(microseconds=1)) == state


def test_published_thresholds_share_the_checkpoint_constants():
    policy = position_freshness_policy()
    assert policy == {
        "version": "southbank-position-freshness-v1",
        "stale_after_seconds": POSITION_STALE_SECONDS,
        "expired_after_seconds": POSITION_EXPIRED_SECONDS,
    }
    policy["stale_after_seconds"] = 0
    assert position_freshness_policy()["stale_after_seconds"] == POSITION_STALE_SECONDS


def test_shared_browser_corpus_matches_the_production_server_evaluator():
    corpus = json.loads(
        (Path(__file__).parents[1] / "fixtures/position-freshness-parity.json").read_text(
            encoding="utf-8"
        )
    )
    assert corpus["policy"] == position_freshness_policy()
    assert len(corpus["cases"]) == 217
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    for case in corpus["cases"]:
        observed = datetime.fromisoformat(case["observed"]) if case["observed"] else None
        at = epoch + timedelta(milliseconds=case["at_ms"])
        assert position_freshness(observed, at) == case["expected"], case

"""Real city delivery metrics through a separate operator CLI process."""

import json
import os
import subprocess
import sys

import pytest
from sqlalchemy import func, update
from test_city_runs import city as city
from test_city_runs import drain
from test_event_store import store as store

from urbanpulse.adapters.event_tables import deliveries
from urbanpulse.application.city_checkpoints import CONSUMER, RESULT_CONSUMER
from urbanpulse.application.durable_delivery import FailureCategory, ReplayReason
from urbanpulse.config import ROOT

pytestmark = pytest.mark.integration


def metrics(city):
    url = city.queue.engine.url.render_as_string(hide_password=False)
    result = subprocess.run(
        [sys.executable, "-m", "workers.city.main", "metrics"],
        cwd=ROOT,
        env=dict(os.environ, DATABASE_URL=url),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout
    return {item["consumer"]: item for item in json.loads(result.stdout)["consumers"]}


def test_empty_queue_needs_no_active_import_or_run(city):
    city, _ = city
    report = metrics(city)
    assert set(report) == {CONSUMER, RESULT_CONSUMER}
    for item in report.values():
        assert item["counts"] == {}
        assert item["backlog_count"] == item["backlog_age_seconds"] == 0
        assert item["retry_count"] == item["dead_letter_count"] == 0


def test_operator_metrics_follow_dead_letter_replay_and_both_consumers(city):
    city, scope = city
    city.create("metrics-demo", scope, "city")
    city.advance("metrics-demo", 60)
    before = city.inspect("metrics-demo")
    queued = metrics(city)
    assert queued[CONSUMER]["backlog_count"] > 0
    assert queued[RESULT_CONSUMER]["backlog_count"] == 0
    assert city.inspect("metrics-demo") == before
    claim = city.queue.claim(CONSUMER)[0]
    city.queue.fail(claim, FailureCategory.HANDLER)
    retrying = metrics(city)
    assert retrying[CONSUMER]["retry_count"] == 1
    # Terminal validation failure is a separate state, not queued retry work.
    with city.queue.engine.begin() as connection:
        connection.execute(
            update(deliveries)
            .where(deliveries.c.id == claim.delivery_id)
            .values(available_at=func.now())
        )
    claim = city.queue.claim(CONSUMER)[0]
    city.queue.fail(claim, FailureCategory.INVALID)
    blocked = metrics(city)
    assert blocked[CONSUMER]["dead_letter_count"] == 1
    assert blocked[CONSUMER]["retry_count"] == 0
    city.queue.replay(claim.delivery_id, claim.generation, ReplayReason.HANDLER_FIXED)
    drain(city)
    recovered = metrics(city)
    for item in recovered.values():
        assert item["backlog_count"] == item["backlog_age_seconds"] == 0
        assert item["retry_count"] == item["dead_letter_count"] == 0
        assert item["counts"]["complete"] > 0
    assert city.inspect("metrics-demo")["completed"] == 60

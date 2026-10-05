"""Durable city checkpoints against the synchronous reference with real PostGIS."""

import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from sqlalchemy import delete, select, update
from test_event_store import URL, count
from test_event_store import store as store

from urbanpulse.adapters.city_fixture import LocalCityCapture, capture_city
from urbanpulse.adapters.city_import import prepare_import
from urbanpulse.adapters.city_run_tables import inbox, runs
from urbanpulse.adapters.city_runs import PostgresCityRuns, context
from urbanpulse.adapters.city_store import CityInputStore, encode
from urbanpulse.adapters.event_recovery import PostgresRecoveryStore
from urbanpulse.adapters.event_tables import deliveries, publications
from urbanpulse.adapters.postgis import PostgisMembership
from urbanpulse.application.city import CityService
from urbanpulse.application.city_checkpoints import CONSUMER, RESULT_CONSUMER, CityRunWorker
from urbanpulse.application.composition import ComposedCityService
from urbanpulse.application.durable_delivery import FailureCategory, ReplayReason
from urbanpulse.application.event_worker import EventWorker
from urbanpulse.application.scenarios import Scenario

pytestmark = pytest.mark.integration


@pytest.fixture
def city(store, tmp_path):
    spatial = PostgisMembership(URL)
    captured = LocalCityCapture(tmp_path, capture_city(tmp_path)).read()
    inputs = CityInputStore(store.engine)
    scope = inputs.save(captured, prepare_import(captured, spatial))
    queue = PostgresRecoveryStore(store.engine)
    city = PostgresCityRuns(queue, inputs, spatial)
    return city, scope


def worker(city):
    return CityRunWorker(
        city,
        EventWorker(city.queue, CONSUMER, city.receive),
        EventWorker(city.queue, RESULT_CONSUMER, city.receive),
    )


def drain(city):
    running = worker(city)
    for _ in range(1000):
        if running.step().status == "idle":
            return
    pytest.fail("durable city worker failed to quiesce")


def canonical(view):
    view = json.loads(encode(view))
    view["composition"].pop("delivery")
    view["composition"].pop("recovery", None)
    return view


@pytest.mark.parametrize("scenario", list(Scenario))
def test_every_completed_checkpoint_matches_synchronous_city(city, scenario):
    city, scope = city
    city.create("pilot", scope, scenario)
    city.advance("pilot", 360)
    assert city.inspect("pilot")["snapshot"] is None
    drain(city)
    result = city.inspect("pilot")
    assert result["completed"] == result["target"] == 360, result
    inputs = city.inputs.load(scope)
    reference = ComposedCityService(CityService(inputs, city.spatial, inputs=inputs), inputs)
    for checkpoint in result["checkpoints"]:
        assert checkpoint["status"] == "complete", checkpoint
        actual = city.inspect("pilot", checkpoint["seconds"])["snapshot"]
        assert canonical(actual) == canonical(reference.snapshot(checkpoint["seconds"], scenario))
    assert city.queue.metrics(CONSUMER)["backlog_count"] == 0
    assert city.queue.metrics(RESULT_CONSUMER)["backlog_count"] == 0


def test_run_creation_and_advance_are_idempotent_and_never_rewind(city):
    city, scope = city
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: city.create("pilot", scope, "city"), range(2)))
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: city.advance("pilot", 60), range(2)))
    assert count(city.queue, runs) == 1
    before = count(city.queue, publications)
    city.advance("pilot", 60)
    assert count(city.queue, publications) == before
    with pytest.raises(ValueError, match="rewind"):
        city.advance("pilot", 59)
    with pytest.raises(ValueError, match="another scope"):
        city.create("pilot", scope, "weather")
    drain(city)
    assert city.inspect("pilot")["completed"] == 60


def test_dead_letter_blocks_only_its_run_and_replay_unblocks_it(city):
    city, scope = city
    city.create("blocked", scope, "city")
    city.advance("blocked", 60)
    claim = city.queue.claim(CONSUMER)[0]
    assert claim.context == context("blocked")
    city.queue.fail(claim, FailureCategory.INVALID)
    city.create("healthy", scope, "city")
    city.advance("healthy", 60)
    drain(city)
    assert city.inspect("healthy")["completed"] == 60
    blocked = city.inspect("blocked")
    assert blocked["completed"] == -1 and blocked["snapshot"] is None
    assert blocked["checkpoints"][0]["blocked_publications"]
    city.queue.replay(claim.delivery_id, claim.generation, ReplayReason.OPERATOR_RETRY)
    drain(city)
    assert city.inspect("blocked")["completed"] == 60


def test_missing_received_input_cannot_be_advertised_as_complete(city):
    city, scope = city
    city.create("pilot", scope, "city")
    city.advance("pilot", 0)
    inputs = EventWorker(city.queue, CONSUMER, city.receive)
    while inputs.step().status != "idle":
        pass
    with city.queue.engine.begin() as connection:
        connection.execute(delete(inbox))
    assert city.progress() is False
    result = city.inspect("pilot")
    assert result["snapshot"] is None and result["completed"] == -1
    assert result["checkpoints"][0]["error"] == "checkpoint-reconstruction-unavailable"


def test_future_checkpoints_are_not_published_before_the_current_barrier(city):
    city, scope = city
    city.create("pilot", scope, "city")
    city.advance("pilot", 360)
    staged = city.inspect("pilot")
    assert staged["checkpoints"][0]["status"] == "pending"
    assert all(c["status"] == "scheduled" for c in staged["checkpoints"][1:])
    claims = city.queue.claim(CONSUMER, limit=100)
    assert len(claims) == 1
    assert city.queue.claim(CONSUMER, limit=100) == ()
    city.queue.complete(
        claims[0], lambda transaction, wire: city.receive(claims[0], transaction, wire)
    )
    assert len(city.queue.claim(CONSUMER, limit=100)) == 1


def test_persisted_expiry_checkpoint_changes_area_without_new_weather_capture(city):
    city, scope = city
    city.create("expiry", scope, "weather-outage")
    city.advance("expiry", 239)
    drain(city)
    before = city.inspect("expiry")["snapshot"]
    assert before["assessment"]["condition"] == "degraded"
    with city.queue.engine.connect() as connection:
        weather_ids = set(
            connection.execute(
                select(publications.c.id).where(
                    publications.c.source == "urn:urbanpulse:fixture:weather"
                )
            ).scalars()
        )
    restarted = PostgresCityRuns(
        PostgresRecoveryStore(city.queue.engine), city.inputs, city.spatial
    )
    restarted.advance("expiry", 240)
    drain(restarted)
    after = restarted.inspect("expiry")["snapshot"]
    assert after["assessment"]["condition"] == "unknown"
    assert len(after["composition"]["area_events"]) == len(before["composition"]["area_events"]) + 1
    with city.queue.engine.connect() as connection:
        assert (
            set(
                connection.execute(
                    select(publications.c.id).where(
                        publications.c.source == "urn:urbanpulse:fixture:weather"
                    )
                ).scalars()
            )
            == weather_ids
        )


def test_read_only_snapshots_and_run_inspection_do_not_publish_or_move_clocks(city):
    city, scope = city
    city.create("pilot", scope, "city")
    city.advance("pilot", 60)
    drain(city)
    before = (count(city.queue, publications), count(city.queue, deliveries), city.inspect("pilot"))
    inputs = city.inputs.load(scope)
    reference = ComposedCityService(CityService(inputs, city.spatial, inputs=inputs), inputs)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda seconds: reference.snapshot(seconds, "city"), (360, 0)))
    assert (
        count(city.queue, publications),
        count(city.queue, deliveries),
        city.inspect("pilot"),
    ) == before


def test_checkpoint_output_and_next_publication_roll_back_together(city, monkeypatch):
    city, scope = city
    city.create("pilot", scope, "city")
    city.advance("pilot", 60)
    inputs = EventWorker(city.queue, CONSUMER, city.receive)
    while inputs.step().status != "idle":
        pass
    original = city.activate

    def fail_after_next_staging(transaction, run):
        original(transaction, run)
        raise RuntimeError("before checkpoint commit")

    monkeypatch.setattr(city, "activate", fail_after_next_staging)
    before = count(city.queue, publications)
    with pytest.raises(RuntimeError):
        city.finish("pilot")
    assert city.inspect("pilot")["completed"] == -1
    assert count(city.queue, publications) == before
    monkeypatch.setattr(city, "activate", original)
    drain(city)
    assert city.inspect("pilot")["completed"] == 60


ROOT = Path(__file__).parents[2]


def process_environment(city):
    # Every application table is in the unique test schema; public exposes only PostGIS functions.
    url = city.queue.engine.url.set(drivername="postgresql")
    url = url.update_query_dict({"options": url.query["options"] + ",public"})
    return dict(
        os.environ, DATABASE_URL=url.render_as_string(hide_password=False), PYTHONPATH=str(ROOT)
    )


@pytest.mark.parametrize("stage", ["producer-staged", "checkpoint-written", "checkpoint-committed"])
def test_process_crash_cannot_publish_a_partial_checkpoint(city, stage):
    city, scope = city
    city.create("crash", scope, "city")
    if stage != "producer-staged":
        city.advance("crash", 0)
        inputs = EventWorker(city.queue, CONSUMER, city.receive)
        while inputs.step().status != "idle":
            pass
    process = subprocess.Popen(
        [sys.executable, str(ROOT / "tests/helpers/city_checkpoint_process.py"), stage],
        cwd=ROOT,
        env=process_environment(city),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        assert pool.submit(process.stdout.readline).result(timeout=20).strip() == stage
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        pool.shutdown(wait=True)
        process.stdout.close()
        process.stderr.close()
    status = city.inspect("crash")
    if stage == "producer-staged":
        assert status["target"] == -1 and status["checkpoints"] == []
        assert count(city.queue, publications) == 0
        city.advance("crash", 0)
    elif stage == "checkpoint-written":
        assert status["completed"] == -1 and status["snapshot"] is None
    else:
        assert status["completed"] == 0
    # A fresh OS process resumes from database state alone.
    resumed = subprocess.Popen(
        [sys.executable, "-m", "workers.city.main", "run"],
        cwd=ROOT,
        env=process_environment(city),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 20
        while (
            city.inspect("crash")["completed"] != 0
            or city.queue.metrics(RESULT_CONSUMER)["backlog_count"]
        ):
            assert time.monotonic() < deadline and resumed.poll() is None
            time.sleep(0.1)
    finally:
        if resumed.poll() is None:
            resumed.kill()
            resumed.wait(timeout=10)
        resumed.stderr.close()
    result = city.inspect("crash")
    assert len(result["snapshot"]["composition"]["area_events"]) == 1
    assert sum(c["status"] == "complete" for c in result["checkpoints"]) == 1


def test_two_workers_complete_each_checkpoint_and_result_once(city):
    city, scope = city
    city.create("parallel", scope, "city")
    city.advance("parallel", 120)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: drain(city), range(2)))
    result = city.inspect("parallel")
    assert result["completed"] == 120
    with city.queue.engine.connect() as connection:
        rows = list(
            connection.execute(select(inbox).where(inbox.c.consumer == RESULT_CONSUMER)).mappings()
        )
    assert len(rows) == len(result["snapshot"]["composition"]["area_events"])


def test_scope_version_mismatch_blocks_only_affected_run(city):
    city, scope = city
    for run_id in ("bad", "good"):
        city.create(run_id, scope, "city")
        city.advance(run_id, 0)
    with city.queue.engine.begin() as connection:
        connection.execute(
            update(runs).where(runs.c.id == "bad").values(run_version="other-version")
        )
    drain(city)
    assert city.inspect("good")["completed"] == 0
    bad = city.inspect("bad")
    assert bad["completed"] == -1 and bad["snapshot"] is None
    assert bad["checkpoints"][0]["error"]

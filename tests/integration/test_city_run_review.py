"""Checkpoint failure isolation and preparation/commit concurrency regressions."""

import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import inspect, select, update
from test_city_runs import city as city
from test_city_runs import drain
from test_event_store import store as store

from urbanpulse.adapters.city_run_tables import checkpoints, runs
from urbanpulse.adapters.city_runs import PostgresCityRuns, context
from urbanpulse.adapters.city_store import encode
from urbanpulse.adapters.event_tables import deliveries, publications
from urbanpulse.application.city_checkpoints import (
    CONSUMER,
    RESULT_CONSUMER,
    CheckpointPublisher,
    CityCheckpointModel,
    clocks,
)
from urbanpulse.application.composition import area_event
from urbanpulse.application.durable_delivery import StorageUnavailable
from urbanpulse.application.event_worker import EventWorker
from urbanpulse.contracts.composition import AreaStatusChanged

pytestmark = pytest.mark.integration


def deliver_inputs(city):
    worker = EventWorker(city.queue, CONSUMER, city.receive)
    while worker.step().status != "idle":
        pass


@pytest.mark.parametrize(
    "fault", ["result-conflict", "invalid-area", "missing-delivery", "next-activation"]
)
def test_bad_checkpoint_does_not_stop_other_runs(city, monkeypatch, fault):
    city, scope = city
    for run_id in ("bad", "healthy"):
        city.create(run_id, scope, "city")
        city.advance(run_id, 60)
    deliver_inputs(city)
    if fault == "result-conflict":
        model = city.model(city.read_run("bad"))
        event = area_event(model.evaluate(0, CheckpointPublisher()), 1).model_dump(mode="json")
        event["data"]["state"]["rule_version"] = "conflicting-policy"
        with city.queue.transaction() as transaction:
            transaction.publish(context("bad"), json.dumps(event), (RESULT_CONSUMER,))
    elif fault == "invalid-area":

        def invalid_once(view, revision):
            monkeypatch.setattr("urbanpulse.adapters.city_runs.area_event", area_event)
            return AreaStatusChanged.model_validate({})

        monkeypatch.setattr("urbanpulse.adapters.city_runs.area_event", invalid_once)
    elif fault == "missing-delivery":
        with city.queue.engine.begin() as connection:
            connection.execute(
                update(checkpoints)
                .where(checkpoints.c.run_id == "bad", checkpoints.c.seconds == 0)
                .values(publications=encode(["missing-publication"]))
            )
    else:
        with city.queue.engine.begin() as connection:
            row = (
                connection.execute(
                    select(checkpoints)
                    .where(checkpoints.c.run_id == "bad", checkpoints.c.seconds > 0)
                    .order_by(checkpoints.c.seconds)
                    .limit(1)
                )
                .mappings()
                .one()
            )
            wires = json.loads(row["manifest"])
            event = json.loads(wires[0])
            event["data"]["state"]["route_id"] = "conflicting-route"
            wires[0] = json.dumps(event)
            connection.execute(
                update(checkpoints)
                .where(checkpoints.c.run_id == "bad", checkpoints.c.seconds == row["seconds"])
                .values(manifest=encode(wires))
            )
    drain(city)
    bad = city.inspect("bad")
    assert bad["completed"] == -1 and bad["snapshot"] is None
    assert bad["checkpoints"][0]["error"]
    assert city.inspect("healthy")["completed"] == 60
    if fault == "next-activation":
        with city.queue.engine.connect() as connection:
            rows = list(
                connection.execute(
                    select(publications.c.id).where(
                        publications.c.context == context("bad"),
                        publications.c.source == "urn:urbanpulse:fixture:location",
                    )
                )
            )
        assert rows == []  # Result publication and cursor rolled back before the error was saved.


def test_advance_prepares_only_new_unfinished_clocks(city, monkeypatch):
    city, scope = city
    city.create("pilot", scope, "city")
    city.advance("pilot", 300)
    drain(city)
    seen = []
    original = CityCheckpointModel.plan

    def record(model, seconds):
        seen.append(seconds)
        return original(model, seconds)

    monkeypatch.setattr(CityCheckpointModel, "plan", record)
    city.advance("pilot", 330)
    expected = [value for value in clocks(city.inputs.load(scope), 330) if value > 300]
    assert seen == expected
    city.advance("pilot", 330)
    assert seen == expected  # Pending manifests are reused, too.
    drain(city)
    assert city.inspect("pilot")["completed"] == 330


def test_loading_and_spatial_reconstruction_do_not_hold_run_locks(city, monkeypatch):
    city, scope = city
    city.create("pilot", scope, "city")
    city.advance("pilot", 0)
    deliver_inputs(city)
    phases = []

    def probe(phase):
        digest = hashlib.sha256(json.dumps(("city-run", "pilot")).encode()).digest()
        with city.queue.engine.begin() as connection:
            assert connection.exec_driver_sql(
                "SELECT pg_try_advisory_xact_lock(%s)", (int.from_bytes(digest[:8], signed=True),)
            ).scalar_one()
            connection.execute(
                select(runs).where(runs.c.id == "pilot").with_for_update(nowait=True)
            ).one()
        phases.append(phase)

    original_model, original_covers = city.model, city.spatial.covers

    def model(run):
        probe("load")
        return original_model(run)

    def covers(*args):
        probe("spatial")
        return original_covers(*args)

    monkeypatch.setattr(city, "model", model)
    monkeypatch.setattr(city.spatial, "covers", covers)
    assert city.finish("pilot")
    assert "load" in phases and "spatial" in phases


@pytest.mark.parametrize("late_error", [False, True])
@pytest.mark.parametrize("concurrent_change", ["checkpoint", "advance"])
def test_stale_preparation_cannot_commit_or_poison_a_later_checkpoint(
    city, monkeypatch, late_error, concurrent_change
):
    city, scope = city
    city.create("pilot", scope, "city")
    city.advance("pilot", 60)
    deliver_inputs(city)
    ready, resume = threading.Event(), threading.Event()
    original = city.model

    def paused_model(run):
        model = original(run)
        evaluate = model.evaluate

        def paused(*args):
            ready.set()
            assert resume.wait(10)
            if late_error:
                raise ValueError("stale evaluation failed")
            return evaluate(*args)

        model.evaluate = paused
        return model

    monkeypatch.setattr(city, "model", paused_model)
    other = PostgresCityRuns(city.queue, city.inputs, city.spatial)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(city.finish, "pilot")
        try:
            assert ready.wait(10)
            if concurrent_change == "checkpoint":
                assert other.finish("pilot")
            else:
                other.advance("pilot", 90)
            before = other.inspect("pilot")
        finally:
            resume.set()
        assert pending.result(timeout=10) is False
    assert other.inspect("pilot") == before
    assert before["completed"] == (0 if concurrent_change == "checkpoint" else -1)
    assert all(row["error"] is None for row in before["checkpoints"])


def test_database_failure_is_retried_without_marking_the_checkpoint_bad(city, monkeypatch):
    city, scope = city
    city.create("pilot", scope, "city")
    city.advance("pilot", 0)
    deliver_inputs(city)

    def unavailable(run):
        raise StorageUnavailable("temporary failure")

    monkeypatch.setattr(city, "model", unavailable)
    with pytest.raises(StorageUnavailable):
        city.progress()
    assert city.inspect("pilot")["checkpoints"][0]["error"] is None


def test_interleaved_duplicates_preserve_one_ordered_lane_without_run_id_list(city):
    city, scope = city
    city.create("pilot", scope, "city")
    city.advance("pilot", 60)
    drain(city)
    run = city.read_run("pilot")
    assert "publications" not in run
    with city.queue.engine.connect() as connection:
        assert "publications" not in {
            column["name"] for column in inspect(connection).get_columns("event01_city_runs")
        }
        rows = list(
            connection.execute(
                select(deliveries)
                .join(publications)
                .where(
                    publications.c.context == context("pilot"), deliveries.c.consumer == CONSUMER
                )
            ).mappings()
        )
        tail = connection.execute(
            select(deliveries.c.id).where(
                deliveries.c.publication_id == run["last_publication"],
                deliveries.c.consumer == CONSUMER,
            )
        ).scalar_one()
    predecessors = [row["predecessor_id"] for row in rows if row["predecessor_id"] is not None]
    assert len(predecessors) == len(rows) - 1 == len(set(predecessors))
    assert {row["id"] for row in rows} - set(predecessors) == {tail}

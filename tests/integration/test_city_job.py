"""Finite worker acceptance through real login roles and real child processes."""

import json
import subprocess
import sys
import threading
import time
from uuid import uuid4

import psycopg
import pytest
from sqlalchemy.engine import make_url

from apps.api.database import ApiDatabase
from tests.integration.test_demo_database import command_environment, invoke, provision_database
from urbanpulse.adapters.city_store import encode, engine_for
from urbanpulse.adapters.event_store import lock
from urbanpulse.adapters.job_database import JobDatabase, JobSessionLost
from urbanpulse.application.city import CityService
from urbanpulse.application.composition import ComposedCityService
from urbanpulse.config import ROOT
from workers.city.job import JobRequest, supervise

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def fixture_database(tmp_path_factory):
    with provision_database() as (_, _, admin, urls):
        result = invoke(
            urls["import"],
            "workers.ingestion.main",
            "--city-fixture",
            RAW_STORAGE_PATH=str(tmp_path_factory.mktemp("city-job")),
        )
        yield admin, urls, json.loads(result)["import_id"]


def job_command(run_id, scope, seconds=360, timeout=30):
    return [
        sys.executable,
        "-m",
        "workers.city.job",
        run_id,
        "--scope",
        scope,
        "--seconds",
        str(seconds),
        "--timeout-seconds",
        str(timeout),
    ]


def run_job(url, run_id, scope, seconds=360, timeout=30):
    result = subprocess.run(
        job_command(run_id, scope, seconds, timeout),
        cwd=ROOT,
        env=command_environment(url),
        capture_output=True,
        text=True,
        timeout=timeout + 15,
    )
    assert not result.stderr, result.stderr
    return result.returncode, json.loads(result.stdout)


def new_run(url, scope, seconds=0):
    name = "job-" + uuid4().hex
    invoke(url, "workers.city.main", "create", name, "--scope", scope, "--scenario", "city")
    invoke(url, "workers.city.main", "advance", name, "--seconds", str(seconds))
    return name


def test_job_completes_only_selected_run_and_repeat_has_no_new_effects(fixture_database):
    admin, urls, scope = fixture_database
    other = new_run(urls["worker"], scope)
    name = "job-" + uuid4().hex
    tagged = make_url(urls["worker"]).update_query_dict({"application_name": name})
    process = subprocess.Popen(
        job_command(name, scope),
        cwd=ROOT,
        env=command_environment(tagged.render_as_string(hide_password=False)),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    peak = 0
    try:
        with psycopg.connect(admin, autocommit=True) as monitor:
            deadline = time.monotonic() + 45
            while process.poll() is None and time.monotonic() < deadline:
                count = monitor.execute(
                    "SELECT count(*) FROM pg_stat_activity WHERE application_name=%s", (name,)
                ).fetchone()[0]
                peak = max(peak, count)
                time.sleep(0.02)
        stdout, stderr = process.communicate(timeout=5)
        assert process.returncode == 0, stdout + stderr
        assert json.loads(stdout)["status"] == "complete"
        assert not stderr
        assert peak == 1
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
    with psycopg.connect(admin) as monitor:
        assert monitor.execute(
            "SELECT completed FROM event01_city_runs WHERE id=%s", (other,)
        ).fetchone() == (-1,)
        assert monitor.execute(
            "SELECT count(*) FROM event01_attempts a "
            "JOIN event01_deliveries d ON d.id=a.delivery_id "
            "JOIN event01_publications p ON p.id=d.publication_id WHERE p.context=%s",
            ("city-run:" + other,),
        ).fetchone() == (0,)
        before = monitor.execute("SELECT count(*) FROM event01_attempts").fetchone()
    assert run_job(urls["worker"], name, scope)[0] == 0
    with psycopg.connect(admin) as monitor:
        assert monitor.execute("SELECT count(*) FROM event01_attempts").fetchone() == before
    final = json.loads(invoke(urls["worker"], "workers.city.main", "inspect", name))["snapshot"]
    database = ApiDatabase(urls["runtime"])
    try:
        inputs = database.inputs.load(scope)
        expected = ComposedCityService(
            CityService(inputs, database.spatial, inputs=inputs), inputs
        ).snapshot(360, "city")
    finally:
        database.close()
    for view in (final, expected):
        view["composition"].pop("delivery")
        view["composition"].pop("recovery", None)
    assert final == json.loads(encode(expected))


def test_overlapping_job_refuses_before_creating_a_run(fixture_database):
    admin, urls, scope = fixture_database
    name = "job-" + uuid4().hex
    owner = JobDatabase(urls["worker"])
    try:
        with owner.engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
        code, result = run_job(urls["worker"], name, scope, seconds=0)
        assert code != 0 and result["status"] == "busy"
        with psycopg.connect(admin) as monitor:
            assert monitor.execute(
                "SELECT count(*) FROM event01_city_runs WHERE id=%s", (name,)
            ).fetchone() == (0,)
    finally:
        owner.close()
    assert run_job(urls["worker"], name, scope, seconds=0)[0] == 0


def test_lost_lock_session_cannot_reconnect_and_write(fixture_database):
    admin, urls, _ = fixture_database
    owner = JobDatabase(urls["worker"])
    identity = uuid4().hex
    try:
        with owner.engine.connect() as connection:
            pid = connection.exec_driver_sql("SELECT pg_backend_pid()").scalar_one()
        with psycopg.connect(admin, autocommit=True) as monitor:
            monitor.execute("SELECT pg_terminate_backend(%s)", (pid,))
        with pytest.raises(JobSessionLost):
            with owner.engine.begin() as connection:
                connection.exec_driver_sql(
                    "INSERT INTO event01_probe_effects VALUES (%s,'source','event')", (identity,)
                )
    finally:
        owner.close()
    with psycopg.connect(admin) as monitor:
        assert monitor.execute(
            "SELECT count(*) FROM event01_probe_effects WHERE context=%s", (identity,)
        ).fetchone() == (0,)


def test_hard_deadline_stops_blocked_sql_and_a_later_invocation_recovers(fixture_database):
    admin, urls, scope = fixture_database
    name = "job-" + uuid4().hex
    engine = engine_for(admin)
    try:
        with engine.begin() as blocker:
            lock(blocker, "city-run", name)
            started = time.monotonic()
            code, result = run_job(urls["worker"], name, scope, seconds=0, timeout=2)
            assert code != 0 and result["status"] == "deadline-exceeded"
            assert time.monotonic() - started < 10
    finally:
        engine.dispose()
    assert run_job(urls["worker"], name, scope, seconds=0)[0] == 0


@pytest.mark.parametrize("failure", ["dead-letter", "checkpoint-error", "missing-delivery"])
def test_job_refuses_failed_or_incomplete_delivery_evidence(fixture_database, failure):
    admin, urls, scope = fixture_database
    name = new_run(urls["worker"], scope)
    with psycopg.connect(admin) as connection:
        if failure == "checkpoint-error":
            connection.execute(
                "UPDATE event01_city_checkpoints SET error='checkpoint-reconstruction-unavailable' "
                "WHERE run_id=%s",
                (name,),
            )
        elif failure == "dead-letter":
            connection.execute(
                "UPDATE event01_deliveries SET status='dead-letter' WHERE publication_id IN "
                "(SELECT id FROM event01_publications WHERE context=%s)",
                ("city-run:" + name,),
            )
        else:
            connection.execute(
                "DELETE FROM event01_deliveries WHERE publication_id IN "
                "(SELECT id FROM event01_publications WHERE context=%s)",
                ("city-run:" + name,),
            )
    code, result = run_job(urls["worker"], name, scope, seconds=30)
    assert code != 0
    assert result["status"] == (
        "invalid-run-or-inputs" if failure == "missing-delivery" else failure
    )


def test_completed_checkpoint_is_not_success_until_result_delivery_finishes(fixture_database):
    admin, urls, scope = fixture_database
    name = "job-" + uuid4().hex
    assert run_job(urls["worker"], name, scope, seconds=0)[0] == 0
    with psycopg.connect(admin) as connection:
        rows = connection.execute(
            "UPDATE event01_deliveries SET status='dead-letter' WHERE consumer='city-results-v1' "
            "AND publication_id IN (SELECT id FROM event01_publications WHERE context=%s) "
            "RETURNING id",
            ("city-run:" + name,),
        ).fetchall()
        assert rows
    code, result = run_job(urls["worker"], name, scope, seconds=0)
    assert code != 0 and result["status"] == "dead-letter"


def test_cancellation_terminates_child_and_releases_execution_lock(fixture_database, monkeypatch):
    admin, urls, scope = fixture_database
    monkeypatch.setenv("DATABASE_URL", urls["worker"])
    monkeypatch.setenv("CACHE_ENABLED", "false")
    name = "job-" + uuid4().hex
    engine = engine_for(admin)
    stop = threading.Event()
    timer = threading.Timer(1.5, stop.set)
    try:
        with engine.begin() as blocker:
            lock(blocker, "city-run", name)
            timer.start()
            assert supervise(JobRequest(name, scope, "city", 0, 30), stop) == "interrupted"
    finally:
        timer.cancel()
        timer.join(timeout=5)
        engine.dispose()
    assert run_job(urls["worker"], name, scope, seconds=0)[0] == 0

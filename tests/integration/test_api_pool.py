"""Real API saturation, transaction recovery and lifespan cleanup under the runtime role."""

import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.pq import TransactionStatus
from sqlalchemy.engine import make_url
from sqlalchemy.exc import TimeoutError

from apps.api.main import app
from tests.integration.test_demo_database import invoke, provision_database
from urbanpulse.application.city import AREA_ID

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def imported_database(tmp_path_factory):
    with provision_database() as (_, _, operator, urls):
        invoke(
            urls["import"],
            "workers.ingestion.main",
            "--city-fixture",
            RAW_STORAGE_PATH=str(tmp_path_factory.mktemp("api-pool")),
        )
        yield operator, urls["runtime"]


@pytest.fixture
def api(imported_database, monkeypatch):
    operator, runtime = imported_database
    name = "pool-test-" + uuid4().hex
    url = make_url(runtime).update_query_dict({"application_name": name})
    monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
    monkeypatch.setenv("CACHE_ENABLED", "false")
    with psycopg.connect(operator, autocommit=True, connect_timeout=3) as monitor:
        with TestClient(app) as client:
            yield client, app.state.database, monitor, name
        assert monitor.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE application_name=%s", (name,)
        ).fetchone() == (0,)


def test_all_api_database_paths_share_two_slots_and_recover_after_saturation(api):
    client, database, monitor, name = api
    snapshot = client.get(f"/api/v1/areas/{AREA_ID}?seconds=0&scenario=city")
    assert snapshot.status_code == 200
    view = snapshot.json()
    paths = [
        "/health/ready",
        f"/api/v1/areas/{AREA_ID}?seconds=360&scenario=city",
        view["geometry_url"],
        view["evidence_url"],
    ]
    with database.engine.connect(), database.engine.connect():
        with ThreadPoolExecutor(max_workers=5) as executor:
            requests = [executor.submit(client.get, path) for path in paths]
            spatial = executor.submit(
                database.spatial.covers,
                {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
                [(0.5, 0.2)],
            )
            started = time.monotonic()
            responses = [future.result(timeout=10) for future in requests]
            with pytest.raises(TimeoutError):
                spatial.result(timeout=10)
            assert time.monotonic() - started < 8
        assert all(response.status_code == 503 for response in responses)
        assert all(
            "password" not in response.text and name not in response.text for response in responses
        )
        assert monitor.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE application_name=%s", (name,)
        ).fetchone() == (2,)
        assert client.get("/health/live").status_code == 200
        assert client.get("/api/v1/fixture").status_code == 200
    for path in paths:
        assert client.get(path).status_code == 200
    assert database.spatial.covers(
        {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}, [(0.5, 0.2)]
    ) == [True]


def test_spatial_sql_failure_rolls_back_before_connection_reuse(api):
    client, database, _, _ = api
    # Hold one slot so the failing query and subsequent probe reuse the other session.
    with database.engine.connect():
        with database.engine.connect() as connection:
            previous_timeout = connection.exec_driver_sql("SHOW statement_timeout").scalar_one()
        with pytest.raises(psycopg.Error):
            database.spatial.covers({"type": "Polygon", "coordinates": "invalid"}, [])
        with database.engine.connect() as connection:
            assert (
                connection.connection.driver_connection.info.transaction_status
                == TransactionStatus.IDLE
            )
            assert (
                connection.exec_driver_sql("SHOW statement_timeout").scalar_one()
                == previous_timeout
            )
        assert client.get("/health/ready").status_code == 200
        assert client.get(f"/api/v1/areas/{AREA_ID}?scenario=city&seconds=120").status_code == 200


def test_disconnected_idle_sessions_are_replaced_within_the_same_bound(api):
    client, database, monitor, name = api
    with database.engine.connect() as first, database.engine.connect() as second:
        pids = [
            connection.exec_driver_sql("SELECT pg_backend_pid()").scalar_one()
            for connection in (first, second)
        ]
    for pid in pids:
        assert monitor.execute("SELECT pg_terminate_backend(%s)", (pid,)).fetchone() == (True,)
    assert client.get("/health/ready").status_code == 200
    assert client.get(f"/api/v1/areas/{AREA_ID}?scenario=city&seconds=360").status_code == 200
    sessions = monitor.execute(
        "SELECT pid FROM pg_stat_activity WHERE application_name=%s", (name,)
    ).fetchall()
    assert 1 <= len(sessions) <= 2
    assert not set(pids) & {row[0] for row in sessions}


def test_next_lifespan_uses_new_resources_without_reusing_old_connections(
    imported_database, monkeypatch
):
    _, runtime = imported_database
    monkeypatch.setenv("CACHE_ENABLED", "false")
    monkeypatch.setenv("DATABASE_URL", runtime)
    with TestClient(app) as client:
        first = app.state.database
        baseline = client.get(f"/api/v1/areas/{AREA_ID}?scenario=city&seconds=180").json()
        assert "assessment" in baseline
    with TestClient(app) as client:
        second = app.state.database
        assert second is not first
        assert second.inputs is not first.inputs
        assert second.spatial is not first.spatial
        assert client.get(f"/api/v1/areas/{AREA_ID}?scenario=city&seconds=180").json() == baseline

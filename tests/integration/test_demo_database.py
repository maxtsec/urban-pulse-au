"""Exercise real login roles in an isolated database on the integration server."""

import json
import os
import secrets
import subprocess
import sys
import time
from contextlib import contextmanager
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from sqlalchemy.engine import make_url

from scripts.compose_smoke import comparable_city_view
from scripts.demo_database import (
    activate_roles,
    bootstrap,
    configure_defaults,
    grant_access,
    role_names,
)
from urbanpulse.config import ROOT

pytestmark = pytest.mark.integration


@contextmanager
def provision_database(*, migrate_schema=True):
    original = os.environ.get(
        "URBANPULSE_TEST_DATABASE_URL",
        "postgresql://urbanpulse:urbanpulse_local@127.0.0.1:5432/urbanpulse",
    )
    database = "bootstrap_test_" + uuid4().hex
    prefix = "test_" + uuid4().hex[:20]
    url = make_url(original).set(database=database).render_as_string(hide_password=False)
    passwords = {key: secrets.token_urlsafe(32) for key in role_names(prefix)}
    with psycopg.connect(original, autocommit=True, connect_timeout=3) as operator:
        operator.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    try:
        with psycopg.connect(url, connect_timeout=3) as admin:
            bootstrap(admin, database=database, prefix=prefix)
            activate_roles(admin, passwords, database=database, prefix=prefix)
        urls = {
            purpose: make_url(url)
            .set(username=name, password=passwords[purpose])
            .render_as_string(hide_password=False)
            for purpose, name in role_names(prefix).items()
        }
        if migrate_schema:
            with psycopg.connect(urls["migrate"], connect_timeout=3) as migration:
                configure_defaults(migration, database=database, prefix=prefix)
            invoke(urls["migrate"], "urbanpulse.adapters.city_store", "migrate")
            with psycopg.connect(urls["migrate"], connect_timeout=3) as migration:
                grant_access(migration, database=database, prefix=prefix)
        yield database, prefix, url, urls
    finally:
        # Only this test's random database and roles; never drop the caller's database.
        with psycopg.connect(original, autocommit=True, connect_timeout=3) as operator:
            operator.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database))
            )
            for name in role_names(prefix).values():
                operator.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(name)))


@pytest.fixture(scope="module")
def provisioned():
    with provision_database() as database:
        yield database


def command_environment(url, **extra):
    return {**os.environ, "DATABASE_URL": url, "CACHE_ENABLED": "false", **extra}


def invoke(url, module, *args, **environment):
    result = subprocess.run(
        [sys.executable, "-m", module, *args],
        cwd=ROOT,
        env=command_environment(url, **environment),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    return result.stdout


def test_real_entrypoints_complete_replay_with_separate_application_logins(tmp_path):
    # A separate database keeps the empty-table permission probes independent.
    with provision_database() as (_, _, _, urls):
        imported = invoke(
            urls["import"],
            "workers.ingestion.main",
            "--city-fixture",
            RAW_STORAGE_PATH=str(tmp_path),
        )
        repeated = invoke(
            urls["import"],
            "workers.ingestion.main",
            "--city-fixture",
            RAW_STORAGE_PATH=str(tmp_path),
        )
        assert json.loads(imported)["import_id"] == json.loads(repeated)["import_id"]
        invoke(urls["worker"], "workers.city.main", "create", "role-flow", "--scenario", "city")
        invoke(urls["worker"], "workers.city.main", "advance", "role-flow", "--seconds", "360")
        log = tmp_path / "worker.log"
        with log.open("w", encoding="utf-8") as output:
            worker = subprocess.Popen(
                [sys.executable, "-m", "workers.city.main", "run"],
                cwd=ROOT,
                env=command_environment(urls["worker"]),
                stdout=output,
                stderr=subprocess.STDOUT,
            )
            try:
                deadline = time.monotonic() + 60
                with psycopg.connect(urls["worker"], autocommit=True, connect_timeout=3) as monitor:
                    while time.monotonic() < deadline:
                        assert worker.poll() is None, log.read_text(encoding="utf-8")
                        completed = monitor.execute(
                            "SELECT completed FROM event01_city_runs WHERE id='role-flow'"
                        ).fetchone()
                        unfinished = monitor.execute(
                            "SELECT count(*) FROM event01_deliveries WHERE status <> 'complete'"
                        ).fetchone()
                        if completed == (360,) and unfinished == (0,):
                            break
                        time.sleep(0.1)
                    else:
                        pytest.fail(
                            "Worker did not finish replay: " + log.read_text(encoding="utf-8")
                        )
            finally:
                worker.terminate()
                try:
                    worker.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    worker.kill()
                    worker.wait(timeout=10)
        durable = json.loads(invoke(urls["worker"], "workers.city.main", "inspect", "role-flow"))
        # A fresh process ensures no app settings/caches from superuser tests survive.
        api = subprocess.run(
            [
                sys.executable,
                "-c",
                """
import json
from fastapi.testclient import TestClient
from apps.api.main import app
from urbanpulse.application.city import AREA_ID
with TestClient(app) as client:
    response = client.get('/health/ready')
    assert response.status_code == 200, response.text
    for seconds in (0, 120, 360):
        response = client.get(
            f'/api/v1/areas/{AREA_ID}', params={'seconds': seconds, 'scenario': 'city'}
        )
        assert response.status_code == 200, response.text
    print(json.dumps(response.json()))
""",
            ],
            cwd=ROOT,
            env=command_environment(urls["runtime"]),
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert api.returncode == 0, api.stderr + api.stdout
        expected = durable["snapshot"]
        actual = json.loads(api.stdout)
        for snapshot in (expected, actual):
            snapshot["composition"].pop("delivery")
            snapshot["composition"].pop("recovery", None)
        assert comparable_city_view(actual) == comparable_city_view(expected)


@contextmanager
def rollback(url):
    with psycopg.connect(url, connect_timeout=3) as connection:
        try:
            yield connection
        finally:
            connection.rollback()


def test_runtime_can_read_spatial_inputs_but_not_write_or_read_worker_state(provisioned):
    _, _, _, urls = provisioned
    with rollback(urls["runtime"]) as connection:
        assert connection.execute("SELECT count(*) FROM city04_imports").fetchone() == (0,)
        assert connection.execute(
            "SELECT ST_Covers(ST_Buffer(ST_Point(0,0),1),ST_Point(0,0))"
        ).fetchone() == (True,)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("UPDATE city04_imports SET capture_id=id WHERE false")
    with rollback(urls["runtime"]) as connection:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("SELECT * FROM event01_receipts")


def test_import_can_write_inputs_and_pointer_but_not_worker_or_immutable_history(provisioned):
    _, _, _, urls = provisioned
    with rollback(urls["import"]) as connection:
        connection.execute("INSERT INTO city04_imports VALUES ('a','b','c','{}','d')")
        connection.execute("INSERT INTO city04_active_imports VALUES ('fixture','a')")
        connection.execute("UPDATE city04_active_imports SET scope='a' WHERE name='fixture'")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("UPDATE city04_imports SET capture_id='changed'")
    with rollback(urls["import"]) as connection:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute(
                "INSERT INTO event01_probe_effects(context,source,event_id) VALUES ('x','y','z')"
            )


def test_worker_can_write_effects_and_update_deliveries_but_not_inputs(provisioned):
    _, _, _, urls = provisioned
    with rollback(urls["worker"]) as connection:
        connection.execute("SELECT * FROM city04_imports")
        connection.execute(
            "INSERT INTO event01_probe_effects(context,source,event_id) VALUES ('x','y','z')"
        )
        connection.execute("UPDATE event01_deliveries SET generation=generation WHERE false")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("INSERT INTO city04_imports VALUES ('a','b','c','{}','d')")


@pytest.mark.parametrize("purpose", ["runtime", "import", "worker"])
def test_app_roles_cannot_escalate_create_or_truncate(provisioned, purpose):
    database, prefix, _, urls = provisioned
    statements = [
        "CREATE TABLE public.forbidden(value int)",
        "CREATE TEMP TABLE forbidden(value int)",
        "TRUNCATE city04_imports CASCADE",
        "DELETE FROM city04_imports WHERE false",
        sql.SQL("SET ROLE {}").format(sql.Identifier(role_names(prefix)["migrate"])),
    ]
    for statement in statements:
        with rollback(urls[purpose]) as connection:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute(statement)
    with rollback(urls[purpose]) as connection:
        assert connection.execute("SELECT current_database()").fetchone() == (database,)
        assert connection.execute(
            "SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls "
            "FROM pg_roles WHERE rolname=current_user"
        ).fetchone() == (False,)


def test_defaults_leave_future_tables_sequences_and_functions_private(provisioned):
    _, prefix, _, urls = provisioned
    reader = role_names(prefix)["runtime"]
    with rollback(urls["migrate"]) as connection:
        connection.execute("CREATE TABLE future_table(id serial)")
        connection.execute(
            "CREATE FUNCTION future_function() RETURNS int LANGUAGE sql AS 'SELECT 1'"
        )
        assert connection.execute(
            "SELECT has_table_privilege(%s,'future_table','SELECT')", (reader,)
        ).fetchone() == (False,)
        assert connection.execute(
            "SELECT has_sequence_privilege(%s,'future_table_id_seq','USAGE')", (reader,)
        ).fetchone() == (False,)
        assert connection.execute(
            "SELECT has_function_privilege(%s,'future_function()','EXECUTE')", (reader,)
        ).fetchone() == (False,)


def test_unknown_tables_stop_access_refresh_and_repeat_bootstrap_does_not_rotate(provisioned):
    database, prefix, admin_url, urls = provisioned
    with rollback(urls["migrate"]) as connection:
        connection.execute("CREATE TABLE unexpected(value int)")
        with pytest.raises(ValueError, match="unexpected application tables"):
            grant_access(connection, database=database, prefix=prefix)
    with rollback(admin_url) as connection:
        with pytest.raises(ValueError, match="role already exists"):
            bootstrap(connection, database=database, prefix=prefix)
        with pytest.raises(ValueError, match="explicit target"):
            bootstrap(connection, database="wrong_database", prefix=prefix)


@pytest.mark.parametrize(
    "purpose,limit", [("runtime", 12), ("migrate", 2), ("import", 3), ("worker", 4)]
)
def test_role_connection_caps_are_enforced_on_real_logins(provisioned, purpose, limit):
    _, _, _, urls = provisioned
    connections = []
    try:
        for _ in range(limit):
            connections.append(psycopg.connect(urls[purpose], connect_timeout=3))
        with pytest.raises(psycopg.OperationalError, match="too many connections for role"):
            psycopg.connect(urls[purpose], connect_timeout=3)
    finally:
        for connection in connections:
            connection.close()


def test_autocommit_and_rotation_are_rejected_without_changing_live_logins(provisioned):
    database, prefix, admin_url, urls = provisioned
    with psycopg.connect(admin_url, autocommit=True, connect_timeout=3) as connection:
        with pytest.raises(ValueError, match="caller-owned transaction"):
            bootstrap(connection, database=database, prefix=prefix)
    with rollback(admin_url) as connection:
        with pytest.raises(ValueError, match="unactivated bootstrap profile"):
            activate_roles(
                connection,
                {key: secrets.token_urlsafe(32) for key in role_names(prefix)},
                database=database,
                prefix=prefix,
            )
    with rollback(urls["runtime"]) as connection:
        assert connection.execute("SELECT 1").fetchone() == (1,)

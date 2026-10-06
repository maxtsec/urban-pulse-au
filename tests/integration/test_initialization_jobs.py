"""Run the packaged initialization entrypoints against real restricted SQL logins."""

import json
import subprocess
import sys
from dataclasses import replace
from uuid import uuid4

import psycopg
import pytest

from apps.api.database import ApiDatabase
from tests.integration.test_demo_database import command_environment, provision_database
from tests.job_evidence import check_job_evidence
from urbanpulse.adapters.city_fixture import LocalCityCapture, capture_city
from urbanpulse.adapters.city_import import prepare_import
from urbanpulse.adapters.city_store import CityInputStore, engine_for
from urbanpulse.adapters.demo_database import EXPECTED_REVISION
from urbanpulse.adapters.job_database import JobDatabase
from urbanpulse.adapters.postgis import PostgisMembership
from urbanpulse.config import ROOT

pytestmark = pytest.mark.integration


def run_job(provisioned, operation, *, purpose=None, timeout=30, **options):
    database, prefix, _, urls = provisioned
    arguments = {
        "database": database,
        "role-prefix": prefix,
        "expected-revision": EXPECTED_REVISION,
        "timeout-seconds": str(timeout),
    } | options
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "workers.initialization.job",
            operation,
            *(item for key, value in arguments.items() for item in ("--" + key, value)),
        ],
        cwd=ROOT,
        env=command_environment(urls[purpose or operation]),
        capture_output=True,
        text=True,
        timeout=timeout + 15,
    )
    parsed = json.loads(result.stdout)
    check_job_evidence(result.stderr, parsed["status"])
    return result.returncode, parsed


@pytest.fixture(scope="module")
def initialized():
    with provision_database(migrate_schema=False) as database:
        code, result = run_job(database, "migrate")
        assert code == 0, result
        assert result["schema_revision"] == EXPECTED_REVISION
        yield database


def test_real_migration_repeat_and_import_are_safe_and_runtime_readable(initialized):
    _, _, admin, urls = initialized
    assert run_job(initialized, "migrate")[0] == 0
    code, imported = run_job(initialized, "import")
    assert code == 0, imported
    scope = imported["import_id"]
    assert run_job(initialized, "import", **{"expected-import-id": scope}) == (0, imported)
    resources = ApiDatabase(urls["runtime"])
    try:
        resources.probe()
        assert resources.inputs.active_scope() == scope
        assert resources.inputs.load(scope).services
    finally:
        resources.close()
    with psycopg.connect(admin) as connection:
        assert connection.execute("SELECT count(*) FROM city04_imports").fetchone() == (1,)
        assert connection.execute("SELECT count(*) FROM event01_publications").fetchone() == (0,)
    with psycopg.connect(urls["runtime"]) as connection:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("DELETE FROM city04_imports WHERE false")


@pytest.mark.parametrize("selected", [False, True])
def test_import_identity_mismatch_writes_no_history_or_pointer(selected, tmp_path):
    with provision_database() as provisioned:
        _, _, admin, urls = provisioned
        if selected:
            captured = LocalCityCapture(tmp_path, capture_city(tmp_path)).read()
            previous = replace(captured, capture_id=uuid4().hex * 2)
            engine = engine_for(urls["import"])
            try:
                store = CityInputStore(engine)
                scope = store.save(
                    previous,
                    prepare_import(previous, PostgisMembership(urls["import"], engine=engine)),
                )
                store.select_import(scope)
            finally:
                engine.dispose()

        tables = ["city04_imports", "city04_active_imports"] + [
            f"city04_{owner}_{kind}"
            for owner in ("transport", "weather", "planning")
            for kind in ("revisions", "observations")
        ]
        with psycopg.connect(admin) as connection:
            before = {
                table: connection.execute(f"SELECT * FROM {table}").fetchall() for table in tables
            }
        code, result = run_job(provisioned, "import", **{"expected-import-id": "0" * 64})
        assert code != 0
        assert result["status"] == "invalid-run-or-inputs"
        with psycopg.connect(admin) as connection:
            for table in tables:
                assert connection.execute(f"SELECT * FROM {table}").fetchall() == before[table]


@pytest.mark.parametrize("operation", ["migrate", "import"])
def test_initialization_joins_worker_execution_lock(initialized, operation):
    database = JobDatabase(initialized[3]["worker"])
    try:
        with database.engine.connect():
            pass
        code, result = run_job(initialized, operation)
        assert code != 0
        assert result["status"] == "busy"
    finally:
        database.close()


@pytest.mark.parametrize(
    "operation,purpose,options",
    [
        ("migrate", "migrate", {"database": "wrong_target"}),
        ("migrate", "runtime", {}),
        ("import", "worker", {}),
        ("migrate", "migrate", {"expected-revision": "head"}),
    ],
)
def test_wrong_target_role_or_revision_fails_closed(initialized, operation, purpose, options):
    code, result = run_job(initialized, operation, purpose=purpose, **options)
    assert code != 0
    assert result["status"] in ("invalid-run-or-inputs", "invalid-job-arguments")


def test_grant_failure_rolls_back_all_migrations():
    with provision_database(migrate_schema=False) as database:
        with psycopg.connect(database[3]["migrate"]) as connection:
            connection.execute("CREATE TABLE unexpected(value int)")
        code, result = run_job(database, "migrate")
        assert code != 0
        assert result["status"] == "invalid-run-or-inputs"
        with psycopg.connect(database[2]) as connection:
            assert connection.execute(
                "SELECT to_regclass('public.alembic_version')"
            ).fetchone() == (None,)
            assert connection.execute("SELECT to_regclass('public.city04_imports')").fetchone() == (
                None,
            )
            connection.execute("DROP TABLE unexpected")
        assert run_job(database, "migrate")[0] == 0


def test_blocked_import_deadline_preserves_selection_and_can_resume(initialized):
    assert run_job(initialized, "import")[0] == 0
    with psycopg.connect(initialized[2]) as connection:
        before = connection.execute("SELECT * FROM city04_active_imports").fetchall()
        connection.execute("LOCK TABLE city04_imports IN ACCESS EXCLUSIVE MODE")
        code, result = run_job(initialized, "import", timeout=2)
        assert code != 0
        assert result["status"] == "deadline-exceeded"
        assert connection.execute("SELECT * FROM city04_active_imports").fetchall() == before
    assert run_job(initialized, "import")[0] == 0


def test_unverifiable_staged_history_cannot_replace_active_selection(initialized, tmp_path):
    assert run_job(initialized, "import")[0] == 0
    _, _, admin, urls = initialized
    captured = LocalCityCapture(tmp_path, capture_city(tmp_path)).read()
    candidate = replace(captured, capture_id=uuid4().hex * 2)
    engine = engine_for(urls["import"])
    try:
        store = CityInputStore(engine)
        previous = store.active_scope()
        scope = store.save(
            candidate, prepare_import(candidate, PostgisMembership(urls["import"], engine=engine))
        )
        with psycopg.connect(admin) as connection:
            connection.execute(
                "UPDATE city04_imports SET content_hash=%s WHERE id=%s", ("0" * 64, scope)
            )
        with pytest.raises(ValueError, match="integrity mismatch"):
            store.select_import(scope)
        assert store.active_scope() == previous
    finally:
        engine.dispose()

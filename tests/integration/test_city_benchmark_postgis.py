"""Real PostGIS benchmark isolation, round-trip replay and cleanup."""

import os

import pytest
from sqlalchemy import inspect, text

from scripts.benchmark_city import benchmark_case, isolated_store
from urbanpulse.adapters.city_fixture import LocalCityCapture, capture_city
from urbanpulse.adapters.city_store import engine_for
from urbanpulse.adapters.postgis import PostgisMembership

pytestmark = pytest.mark.integration
URL = os.environ.get(
    "URBANPULSE_TEST_DATABASE_URL",
    "postgresql://urbanpulse:urbanpulse_local@127.0.0.1:5432/urbanpulse",
)


def test_benchmark_uses_fresh_schema_without_activating_import(tmp_path):
    base = LocalCityCapture(tmp_path, capture_city(tmp_path)).read()
    with isolated_store(URL) as store:
        with store.engine.connect() as connection:
            schema = connection.execute(text("SELECT current_schema()")).scalar_one()
        assert schema.startswith("urbanpulse_bench_")
        case = benchmark_case(store, base, PostgisMembership(URL), 3, 2, 1)
        assert case["snapshots"] == 3
        assert case["copy_profile"]["planning_calls"] > 3
        with pytest.raises(ValueError):
            store.active_scope()
    engine = engine_for(URL)
    try:
        assert schema not in inspect(engine).get_schema_names()
    finally:
        engine.dispose()


def test_failing_benchmark_still_removes_only_its_created_schema():
    with pytest.raises(RuntimeError, match="benchmark interrupted"):
        with isolated_store(URL) as store:
            with store.engine.connect() as connection:
                schema = connection.execute(text("SELECT current_schema()")).scalar_one()
            raise RuntimeError("benchmark interrupted")
    engine = engine_for(URL)
    try:
        assert schema not in inspect(engine).get_schema_names()
        assert "public" in inspect(engine).get_schema_names()
    finally:
        engine.dispose()


def test_stripped_connection_options_abort_before_migrations(monkeypatch):
    from sqlalchemy import make_url

    from scripts import benchmark_city

    def stripped_engine(url):
        parsed = make_url(url)
        if "options" in parsed.query:
            parsed = parsed.difference_update_query(["options"])
        return engine_for(parsed.render_as_string(hide_password=False))

    def forbidden_migration(*args, **kwargs):
        pytest.fail("migration must not run on an unverified schema")

    monkeypatch.setattr(benchmark_city, "engine_for", stripped_engine)
    monkeypatch.setattr(benchmark_city, "migrate", forbidden_migration)
    with pytest.raises(RuntimeError, match="isolation"):
        with isolated_store(URL):
            pytest.fail("unverified store must not escape")


def test_schema_is_rechecked_before_subsequent_store_transactions():
    with isolated_store(URL) as store:
        # Simulate session settings changing after the migration preflight.
        with store.engine.connect() as connection:
            connection.execute(text("SET search_path TO public"))
            connection.commit()
        with pytest.raises(RuntimeError, match="isolation"):
            store.active_scope()

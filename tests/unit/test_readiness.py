"""Basic API readiness is independent of city fixture import and reconstruction."""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import psycopg
import pytest
from fastapi.testclient import TestClient
from redis.exceptions import RedisError

from apps.api.main import app
from urbanpulse.config import Settings


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    monkeypatch.setenv("CACHE_ENABLED", "true")
    monkeypatch.setattr("apps.api.main.Settings", lambda: Settings(_env_file=None))


def test_ready_does_not_load_city_history_and_smoke_fixture_still_works(monkeypatch):
    monkeypatch.setattr("apps.api.main.psycopg.connect", MagicMock())
    monkeypatch.setattr("apps.api.main.Redis.from_url", MagicMock())

    class EmptyStore:
        def active_scope(self):
            raise ValueError("no city import")

        def load(self, scope):
            pytest.fail("readiness must not load city history")

    monkeypatch.setattr("apps.api.city.input_store", lambda: EmptyStore())
    with TestClient(app) as client:
        assert client.get("/health/ready").json() == {
            "status": "ok",
            "postgis": "ok",
            "redis": "ok",
            "mode": "fixture",
        }
        assert client.get("/api/v1/fixture").status_code == 200
        assert client.get("/api/v1/areas/au-vic-melbourne-clue-southbank").status_code == 503


@pytest.mark.parametrize("dependency", ["postgres", "redis"])
def test_dependency_failure_is_still_not_ready(monkeypatch, dependency):
    postgres = MagicMock(
        side_effect=psycopg.OperationalError() if dependency == "postgres" else None
    )
    redis = MagicMock(side_effect=RedisError() if dependency == "redis" else None)
    monkeypatch.setattr("apps.api.main.psycopg.connect", postgres)
    monkeypatch.setattr("apps.api.main.Redis.from_url", redis)
    with TestClient(app) as client:
        assert client.get("/health/ready").status_code == 503


@pytest.mark.parametrize("cache_enabled", ["true", "false"])
def test_postgis_query_failure_is_not_ready_in_either_mode(monkeypatch, cache_enabled):
    monkeypatch.setenv("CACHE_ENABLED", cache_enabled)
    postgres = MagicMock()
    postgres.return_value.__enter__.return_value.execute.side_effect = psycopg.OperationalError()
    redis = MagicMock()
    monkeypatch.setattr("apps.api.main.psycopg.connect", postgres)
    monkeypatch.setattr("apps.api.main.Redis.from_url", redis)
    with TestClient(app) as client:
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json() == {"detail": "PostGIS is unavailable"}
        assert client.get("/health/live").status_code == 200
    redis.assert_not_called()


def test_disabled_cache_never_constructs_redis_client(monkeypatch):
    monkeypatch.setenv("CACHE_ENABLED", "false")
    monkeypatch.setenv("REDIS_URL", "unused-even-if-invalid")
    postgres = MagicMock()
    redis = MagicMock(side_effect=AssertionError("Redis must not be contacted"))
    monkeypatch.setattr("apps.api.main.psycopg.connect", postgres)
    monkeypatch.setattr("apps.api.main.Redis.from_url", redis)
    with TestClient(app) as client:
        response = client.get("/health/ready")
        assert response.status_code == 200
        assert response.json() == {
            "status": "ok",
            "postgis": "ok",
            "redis": "disabled",
            "mode": "fixture",
        }
        assert client.get("/api/v1/fixture").status_code == 200
    postgres.return_value.__enter__.return_value.execute.assert_called_once_with(
        "SELECT PostGIS_Version()"
    )
    redis.assert_not_called()


@pytest.mark.parametrize("failure", [RedisError(), OSError()])
def test_enabled_cache_ping_failure_is_not_ready(monkeypatch, failure):
    redis = MagicMock()
    redis.return_value.__enter__.return_value.ping.side_effect = failure
    monkeypatch.setattr("apps.api.main.psycopg.connect", MagicMock())
    monkeypatch.setattr("apps.api.main.Redis.from_url", redis)
    with TestClient(app) as client:
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json() == {"detail": "Local dependencies are unavailable"}


def test_invalid_cache_configuration_stops_startup_before_dependency_checks(monkeypatch):
    monkeypatch.setenv("CACHE_ENABLED", "disabled")
    postgres, redis = MagicMock(), MagicMock()
    monkeypatch.setattr("apps.api.main.psycopg.connect", postgres)
    monkeypatch.setattr("apps.api.main.Redis.from_url", redis)
    with pytest.raises(RuntimeError, match="Invalid application configuration"):
        with TestClient(app):
            pytest.fail("invalid settings must not start the application")
    postgres.assert_not_called()
    redis.assert_not_called()


def test_readiness_reuses_settings_validated_at_startup(monkeypatch):
    settings = MagicMock(return_value=Settings(_env_file=None, cache_enabled=False))
    monkeypatch.setattr("apps.api.main.Settings", settings)
    monkeypatch.setattr("apps.api.main.psycopg.connect", MagicMock())
    with TestClient(app) as client:
        for _ in range(2):
            assert client.get("/health/ready").json()["redis"] == "disabled"
    settings.assert_called_once_with()


def test_uvicorn_exits_on_invalid_configuration_without_logging_input_values():
    invalid = "synthetic-sensitive-invalid-value"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "apps.api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "0",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "CACHE_ENABLED": invalid},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "Invalid application configuration" in output
    assert "Application startup failed" in output
    assert invalid not in output
    assert "ValidationError" not in output

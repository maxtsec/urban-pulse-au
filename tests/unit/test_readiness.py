"""Basic API readiness is independent of city fixture import and reconstruction."""

from unittest.mock import MagicMock

import psycopg
import pytest
from fastapi.testclient import TestClient
from redis.exceptions import RedisError

from apps.api.main import app


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

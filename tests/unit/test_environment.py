from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from apps.api.main import app
from urbanpulse.config import Settings
from workers.ingestion.main import capture


def test_fixture_is_explicit_and_preserves_unknown_delay() -> None:
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        response = client.get("/api/v1/fixture")
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "fixture"
    assert payload["provider"] == "synthetic"
    assert payload["observations"][1]["delay_seconds"] is None
    assert payload["observations"][2]["delay_seconds"] < 0


def test_repeat_capture_keeps_same_content_identity(tmp_path: Path) -> None:
    first = capture(tmp_path)
    assert capture(tmp_path) == first
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_cache_is_enabled_by_default_and_configurable(monkeypatch) -> None:
    monkeypatch.delenv("CACHE_ENABLED", raising=False)
    assert Settings(_env_file=None).cache_enabled is True
    monkeypatch.setenv("CACHE_ENABLED", "false")
    assert Settings(_env_file=None).cache_enabled is False
    monkeypatch.setenv("CACHE_ENABLED", "typo")
    with pytest.raises(ValidationError, match="cache_enabled"):
        Settings(_env_file=None)

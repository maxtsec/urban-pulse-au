"""Smoke failures stay actionable, including cleanup failures and optimized Python."""

import json
import subprocess
import sys
import urllib.error
from copy import deepcopy
from unittest.mock import MagicMock

import pytest

from scripts import compose_smoke


@pytest.fixture
def smoke(monkeypatch, tmp_path):
    monkeypatch.setattr(compose_smoke, "ROOT", tmp_path)
    monkeypatch.setattr(compose_smoke, "verify_database_restart", lambda *args: None)
    monkeypatch.setattr(compose_smoke, "verify_city_checkpoints", lambda *args: None)
    monkeypatch.setattr(compose_smoke, "verify_cache_modes", lambda *args: None)
    commands = []
    worker_results = iter(
        [
            {},
            {"status": "apply", "delivery_id": "probe-delivery", "generation": 1},
            {},
            {"status": "duplicate"},
        ]
    )

    def run(command, **kwargs):
        commands.append(command)
        if "workers.events.main" in command:
            return subprocess.CompletedProcess(command, 0, json.dumps(next(worker_results)), "")
        if "workers.city.main" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                json.dumps(
                    {
                        "consumers": [
                            {"consumer": "city-location-v1"},
                            {"consumer": "city-results-v1"},
                        ]
                    }
                ),
                "",
            )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(compose_smoke.subprocess, "run", run)

    def output(command, **kwargs):
        if command[:2] in (["docker", "container"], ["docker", "network"], ["docker", "volume"]):
            return ""
        return "127.0.0.1:8000"

    monkeypatch.setattr(compose_smoke.subprocess, "check_output", output)
    view = {
        "composition": {"recovery": "persisted-domain-inputs"},
        "geometry_url": "/boundary",
        "evidence_url": "/evidence",
    }
    views = [deepcopy(view) for _ in range(6)]
    area_calls = 0

    def urlopen(endpoint, **kwargs):
        nonlocal area_calls
        body = {}
        if "/areas/" in endpoint:
            area_calls += 1
            if area_calls == 1:
                raise urllib.error.HTTPError(endpoint, 503, "Not imported", {}, None)
            body = views[area_calls - 2]
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.read.return_value = json.dumps(body).encode()
        return response

    monkeypatch.setattr(compose_smoke.urllib.request, "urlopen", urlopen)
    return commands, views


def test_cleanup_failure_preserves_original_failure(monkeypatch, smoke):
    original = RuntimeError("original build failure")
    commands, _ = smoke

    def run(command, **kwargs):
        commands.append(command)
        if "down" in command:
            raise OSError("cleanup unavailable")
        raise original

    monkeypatch.setattr(compose_smoke.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="original build failure") as caught:
        compose_smoke.main()
    assert caught.value is original
    assert "cleanup unavailable" in original.__notes__[0]
    assert "down" in commands[-1]


def test_cleanup_failure_after_success_is_not_silenced(monkeypatch, smoke):
    successful_run = compose_smoke.subprocess.run

    def run(command, **kwargs):
        if "down" in command:
            return subprocess.CompletedProcess(command, 1)
        return successful_run(command, **kwargs)

    monkeypatch.setattr(compose_smoke.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="Compose down .* failed"):
        compose_smoke.main()


@pytest.mark.parametrize("index", [1, 2, 3, 4, 5])
def test_response_mismatch_fails_and_still_cleans_up(smoke, index):
    commands, views = smoke
    views[index]["changed"] = True
    with pytest.raises(RuntimeError, match="city response changed"):
        compose_smoke.main()
    assert "down" in commands[-1]


@pytest.mark.parametrize("view", [[], {"composition": {"recovery": "raw-files"}}])
def test_invalid_city_response_fails_and_still_cleans_up(smoke, view):
    commands, views = smoke
    views[0] = view
    with pytest.raises(RuntimeError, match="city response must"):
        compose_smoke.main()
    assert "down" in commands[-1]


def test_response_check_remains_active_with_optimized_python():
    result = subprocess.run(
        [
            sys.executable,
            "-O",
            "-c",
            "from scripts.compose_smoke import require_equal; "
            "require_equal({}, {'changed': True}, 'probe')",
        ],
        cwd=compose_smoke.ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "probe: city response changed" in result.stderr


def test_cache_mode_failure_still_cleans_up(monkeypatch, smoke):
    commands, _ = smoke

    def fail(*args):
        raise RuntimeError("cache mode check failed")

    monkeypatch.setattr(compose_smoke, "verify_cache_modes", fail)
    with pytest.raises(RuntimeError, match="cache mode check failed"):
        compose_smoke.main()
    assert "down" in commands[-1]


def test_cleanup_enables_every_profile_and_checks_all_resource_types(monkeypatch, smoke):
    commands, _ = smoke
    queried = []
    original = compose_smoke.subprocess.check_output

    def output(command, **kwargs):
        if command[:2] in (["docker", "container"], ["docker", "network"], ["docker", "volume"]):
            queried.append(command)
        return original(command, **kwargs)

    monkeypatch.setattr(compose_smoke.subprocess, "check_output", output)
    compose_smoke.main()
    cleanup = commands[-1]
    down = cleanup.index("down")
    assert cleanup[down - 2 : down] == ["--profile", "*"]
    assert cleanup[down:] == ["down", "--volumes", "--remove-orphans"]
    project = cleanup[cleanup.index("--project-name") + 1]
    assert [q[1] for q in queried] == ["container", "network", "volume"]
    assert "--all" in queried[0]
    assert all(q[-1] == f"label=com.docker.compose.project={project}" for q in queried)


@pytest.mark.parametrize("resource", ["container", "network", "volume"])
def test_cleanup_reports_surviving_resources(monkeypatch, resource):
    monkeypatch.setattr(
        compose_smoke.subprocess,
        "check_output",
        lambda command, **kwargs: "leftover\n" if command[1] == resource else "",
    )
    with pytest.raises(RuntimeError, match=f"labelled resources:.*{resource}.*leftover"):
        compose_smoke.cleanup_stack("urbanpulse-smoke-0123456789ab", MagicMock())


@pytest.mark.parametrize(
    "project", ["urbanpulse", "urbanpulse-smoke-", "urbanpulse-smoke-0123456789abc"]
)
def test_cleanup_refuses_non_smoke_projects_before_running_docker(monkeypatch, project):
    run, query = MagicMock(), MagicMock()
    monkeypatch.setattr(compose_smoke.subprocess, "check_output", query)
    with pytest.raises(RuntimeError, match="invalid isolated cleanup target"):
        compose_smoke.cleanup_stack(project, run)
    run.assert_not_called()
    query.assert_not_called()


def test_leftovers_do_not_hide_an_earlier_smoke_failure(monkeypatch, smoke):
    original = RuntimeError("original build failure")
    successful_run = compose_smoke.subprocess.run

    def run(command, **kwargs):
        if "build" in command:
            raise original
        return successful_run(command, **kwargs)

    monkeypatch.setattr(compose_smoke.subprocess, "run", run)
    monkeypatch.setattr(
        compose_smoke.subprocess, "check_output", lambda *args, **kwargs: "leftover\n"
    )
    with pytest.raises(RuntimeError, match="original build failure") as caught:
        compose_smoke.main()
    assert caught.value is original
    assert "labelled resources" in original.__notes__[0]

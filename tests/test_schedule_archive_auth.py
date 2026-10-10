"""Local seeding cannot turn a cloud check into a developer credential path."""

import subprocess
from dataclasses import replace
from types import SimpleNamespace

import pytest

from urbanpulse.adapters import gtfs_archive_auth as auth
from workers.schedule_archive.main import ArchiveRequest

SA = "urbanpulse-gtfs-archive@example-project.iam.gserviceaccount.com"


def seed_request():
    return ArchiveRequest("seed", "example-archive", SA, "test", "source.zip", "provenance.json")


@pytest.mark.parametrize("operation", ["check", "inspect"])
def test_only_seed_allows_operator_identity(operation):
    with pytest.raises(ValueError, match="only allowed for seed"):
        replace(seed_request(), operation=operation, seed_user_account="operator@example.com")


@pytest.mark.parametrize("account", [SA, "", "--flags-file=secret", "a@b.com&bad", "a\nb@c.com"])
def test_invalid_operator_account_is_rejected(account):
    with pytest.raises(ValueError):
        replace(seed_request(), seed_user_account=account)


def test_seed_requests_only_the_explicit_target_and_captures_token(monkeypatch):
    calls = []
    monkeypatch.setattr(auth.shutil, "which", lambda name: "gcloud")
    monkeypatch.setenv("CLOUDSDK_AUTH_ACCESS_TOKEN", "unwanted-token")

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout="opaque-token\n", stderr="")

    monkeypatch.setattr(auth.subprocess, "run", run)
    assert auth.access_token(SA, "operator@example.com") == "opaque-token"
    argv, options = calls[0]
    assert "--account=operator@example.com" in argv
    assert "--impersonate-service-account=" + SA in argv
    assert "--lifetime=900" in argv
    assert options["capture_output"] and options["timeout"] == 60
    assert "CLOUDSDK_AUTH_ACCESS_TOKEN" not in options["env"]
    assert options["env"]["CLOUDSDK_CORE_LOG_HTTP"] == "false"
    assert not options.get("shell", False)


@pytest.mark.parametrize("failure", ["exit", "timeout", "missing", "bad-token"])
def test_auth_errors_do_not_disclose_subprocess_output(monkeypatch, failure, capsys):
    monkeypatch.setattr(
        auth.shutil, "which", lambda name: None if failure == "missing" else "gcloud"
    )

    def run(*args, **kwargs):
        if failure == "timeout":
            raise subprocess.TimeoutExpired("gcloud", 60, output="sensitive-value")
        return SimpleNamespace(
            returncode=1 if failure == "exit" else 0,
            stdout="sensitive-value\nunexpected-line",
            stderr="sensitive-value",
        )

    monkeypatch.setattr(auth.subprocess, "run", run)
    with pytest.raises(ValueError) as error:
        auth.access_token(SA, "operator@example.com")
    assert "sensitive-value" not in str(error.value)
    assert capsys.readouterr() == ("", "")


def test_cloud_mode_never_calls_gcloud(monkeypatch):
    class Credentials:
        service_account_email = SA
        token = "cloud-token"

        def refresh(self, request):
            pass

    def forbidden(*args, **kwargs):
        raise AssertionError("developer credentials are forbidden")

    monkeypatch.setattr(auth.compute_engine, "Credentials", Credentials)
    monkeypatch.setattr(auth.subprocess, "run", forbidden)
    assert auth.access_token(SA, None) == "cloud-token"


@pytest.mark.parametrize("target", ["", "operator@example.com", SA + "&bad"])
def test_target_must_be_an_explicit_service_account(target, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("authentication must not start")

    monkeypatch.setattr(auth.subprocess, "run", forbidden)
    monkeypatch.setattr(auth.compute_engine, "Credentials", forbidden)
    with pytest.raises(ValueError, match="target service account"):
        auth.access_token(target, "operator@example.com")

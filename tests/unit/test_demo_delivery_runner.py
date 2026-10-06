"""Exercise durable intent/lock and failure handling through the real runner entrypoint."""

import json
import subprocess
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from google.api_core.exceptions import PreconditionFailed

from scripts import demo_delivery_runner as runner
from tests.unit.test_demo_delivery import BUILD, MANIFEST, METADATA, candidate_plan, current


class Blob:
    def __init__(self):
        self.generation = None
        self.value = None

    def upload_from_string(self, value, if_generation_match):
        if if_generation_match != (self.generation or 0):
            raise PreconditionFailed("generation differs")
        self.generation = (self.generation or 0) + 1
        self.value = value

    def upload_from_filename(self, filename, if_generation_match):
        self.upload_from_string(Path(filename).read_bytes(), if_generation_match)

    def reload(self):
        pass

    def download_as_bytes(self, if_generation_match):
        assert if_generation_match == self.generation
        return self.value.encode()

    def delete(self, if_generation_match):
        assert if_generation_match == self.generation
        self.value = None
        self.generation = None


def setup_runner(monkeypatch, tmp_path, failure=None):
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "image_inputs_changed", lambda *_: True)
    monkeypatch.setattr(runner.time, "sleep", lambda _: None)
    (tmp_path / "infra/demo-serving").mkdir(parents=True)
    environment = {
        "DELIVERY_OPERATION": "candidate",
        "GITHUB_REPOSITORY": runner.REPOSITORY,
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_EVENT_NAME": "workflow_run",
        "GITHUB_SHA": BUILD.source_sha,
        "GITHUB_RUN_ID": "10",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_STEP_SUMMARY": str(tmp_path / "summary"),
        "PUBLICATION_RUN": "123",
        "PUBLICATION_ATTEMPT": "1",
        "DEMO_STATE_BUCKET": "example-private-bucket",
        "GCP_PROJECT_ID": "example-project",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(runner, "fetch_publication", lambda *_: deepcopy(MANIFEST))
    monkeypatch.setattr(runner, "github", lambda _: {"commit": {"sha": BUILD.source_sha}})
    credentials = SimpleNamespace(token="never-print-this", refresh=lambda *_: None)
    monkeypatch.setattr(runner.google.auth, "default", lambda **_: (credentials, "example-project"))
    blobs = {}

    def blob(name):
        return blobs.setdefault(name, Blob())

    blob("delivery/current.json").upload_from_string(json.dumps(current()), 0)
    monkeypatch.setattr(
        runner.storage,
        "Client",
        lambda **_: SimpleNamespace(bucket=lambda _: SimpleNamespace(blob=blob)),
    )
    monkeypatch.setattr(runner, "image_metadata", lambda *_: deepcopy(METADATA))
    calls = []

    def command(args, **kwargs):
        calls.append(args)
        if args[:3] == ["docker", "image", "inspect"]:
            return json.dumps(
                [
                    {
                        "RepoDigests": [args[-1]],
                        "Architecture": "amd64",
                        "Os": "linux",
                        "Config": {
                            "Labels": {
                                "org.opencontainers.image.revision": BUILD.source_sha,
                                "org.opencontainers.image.source": "https://github.com/maxtsec/urban-pulse-au",
                            }
                        },
                    }
                ]
            )
        return ""

    monkeypatch.setattr(runner, "command", command)
    inputs, planned = candidate_plan()
    baseline = deepcopy(planned)
    for resource in baseline["resource_changes"]:
        resource["change"]["actions"] = ["no-op"]

    def terraform(root, *args):
        calls.append(list(args))
        if args[0] == "apply" and failure == "apply":
            raise RuntimeError("private diagnostic")
        if args[:2] == ("state", "pull"):
            return json.dumps({"resources": ["existing"]})
        if args[0] == "plan":
            out = next(a[5:] for a in args if a.startswith("-out="))
            Path(out).write_bytes(b"saved-private-plan")
        if args[:2] == ("show", "-json"):
            plan = deepcopy(baseline if "baseline" in args[-1] else planned)
            if failure == "guard" and "baseline" not in args[-1]:
                plan["resource_changes"] = []
            return json.dumps(plan)
        return ""

    monkeypatch.setattr(runner, "terraform", terraform)
    revision = inputs["name_prefix"] + "-" + inputs["release_id"]
    service = {
        "terminalCondition": {"state": "CONDITION_SUCCEEDED"},
        "iapEnabled": True,
        "invokerIamDisabled": False,
        "trafficStatuses": [
            {"revision": current()["inputs"]["serving_revision"], "percent": 100},
            {"revision": revision, "percent": 0, "tag": "candidate"},
        ],
    }
    deployed = {
        "conditions": [{"type": "Ready", "state": "CONDITION_SUCCEEDED"}],
        "containers": [{"name": c, "image": inputs[c + "_image"]} for c in ("api", "web")],
    }
    if failure == "readback":
        deployed["conditions"] = []

    def get(url, **kwargs):
        return SimpleNamespace(
            status_code=200, json=lambda: deployed if "/revisions/" in url else service
        )

    monkeypatch.setattr(runner, "AuthorizedSession", lambda _: SimpleNamespace(get=get))
    return blobs, calls


def test_real_entrypoint_records_candidate_without_promoting(monkeypatch, tmp_path):
    blobs, calls = setup_runner(monkeypatch, tmp_path)
    runner.main()
    record = json.loads(blobs["delivery/current.json"].value)
    assert record["serving"] == current()["serving"]
    assert record["candidate"]["revision"].endswith("d10a1")
    assert record["in_progress"] is None
    assert blobs["delivery/operation.lock"].value is None
    assert sum(c[0] == "apply" for c in calls) == 1
    assert "never-print-this" not in (tmp_path / "summary").read_text()


@pytest.mark.parametrize("failure", ["apply", "readback"])
def test_interrupted_mutation_keeps_durable_intent_lock_and_serving_record(
    monkeypatch, tmp_path, failure
):
    blobs, _ = setup_runner(monkeypatch, tmp_path, failure)
    with pytest.raises((ValueError, RuntimeError)):
        runner.main()
    record = json.loads(blobs["delivery/current.json"].value)
    assert record["serving"] == current()["serving"]
    assert record["candidate"] is None
    assert record["in_progress"]["id"] == "d10a1"
    assert blobs["delivery/operation.lock"].value is not None


def test_rejected_plan_never_applies_and_releases_lock(monkeypatch, tmp_path):
    blobs, calls = setup_runner(monkeypatch, tmp_path, "guard")
    with pytest.raises(ValueError):
        runner.main()
    assert not any(c[0] == "apply" for c in calls)
    assert json.loads(blobs["delivery/current.json"].value) == current()
    assert blobs["delivery/operation.lock"].value is None


def test_stale_publication_is_rejected_again_before_apply(monkeypatch, tmp_path):
    blobs, calls = setup_runner(monkeypatch, tmp_path)
    heads = iter([BUILD.source_sha, "e" * 40])
    monkeypatch.setattr(runner, "github", lambda _: {"commit": {"sha": next(heads)}})
    with pytest.raises(ValueError, match="superseded"):
        runner.main()
    assert not any(c[0] == "apply" for c in calls)
    assert json.loads(blobs["delivery/current.json"].value) == current()
    assert blobs["delivery/operation.lock"].value is None


def test_promotion_fails_before_credentials_if_environment_approval_is_missing(
    monkeypatch, tmp_path
):
    blobs, calls = setup_runner(monkeypatch, tmp_path)
    monkeypatch.setenv("DELIVERY_OPERATION", "promote")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    monkeypatch.setenv("ACCEPTED_CANDIDATE", "true")
    monkeypatch.setattr(runner, "github", lambda _: {"protection_rules": []})
    with pytest.raises(ValueError, match="require approval"):
        runner.main()
    assert not calls
    assert json.loads(blobs["delivery/current.json"].value) == current()


def test_active_operation_lock_rejects_overlapping_delivery(monkeypatch, tmp_path):
    blobs, calls = setup_runner(monkeypatch, tmp_path)
    from scripts.demo_delivery_runner import encode

    # A different owner already holds the generation-checked object.
    lock = Blob()
    lock.upload_from_string(encode({"id": "other"}), 0)
    blobs["delivery/operation.lock"] = lock
    with pytest.raises(runner.DeliveryLocked, match="pre-intent lock recovery"):
        runner.main()
    assert not calls
    assert json.loads(lock.value)["id"] == "other"
    assert json.loads(blobs["delivery/current.json"].value)["in_progress"] is None
    assert "existing operation" in (tmp_path / "summary").read_text(encoding="utf-8")
    assert not any(name.endswith("failure.json") for name in blobs)


def test_readback_waits_for_candidate_traffic_metadata(monkeypatch):
    inputs, _ = candidate_plan()
    revision = inputs["name_prefix"] + "-" + inputs["release_id"]
    ready = {
        "terminalCondition": {"state": "CONDITION_SUCCEEDED"},
        "iapEnabled": True,
        "trafficStatuses": [
            {"revision": inputs["serving_revision"], "percent": 100},
            {"revision": revision, "tag": "candidate", "percent": 0},
        ],
    }
    incomplete = deepcopy(ready)
    incomplete["trafficStatuses"].pop()
    services = iter([incomplete, ready])
    deployed = {
        "conditions": [{"type": "Ready", "state": "CONDITION_SUCCEEDED"}],
        "containers": [{"name": c, "image": inputs[c + "_image"]} for c in ("api", "web")],
    }

    def get(url, **kwargs):
        value = deployed if "/revisions/" in url else next(services)
        return SimpleNamespace(status_code=200, json=lambda: value)

    waits = []
    monkeypatch.setattr(runner.time, "sleep", waits.append)
    runner.read_back(SimpleNamespace(get=get), "https://example/service", inputs, "candidate")
    assert waits == [5]


@pytest.mark.parametrize("has_candidate", [False, True])
def test_unchanged_image_inputs_preserve_retained_candidate(monkeypatch, tmp_path, has_candidate):
    blobs, calls = setup_runner(monkeypatch, tmp_path)
    before = current()
    if has_candidate:
        inputs, _ = candidate_plan()
        inputs["source_sha"] = "d" * 40
        before["candidate"] = {"revision": "reviewing", "inputs": inputs}
        before["inputs"] = inputs
    blobs["delivery/current.json"].upload_from_string(json.dumps(before), 1)
    compared = []

    def unchanged(*args):
        compared.append(args)
        return False

    monkeypatch.setattr(runner, "image_inputs_changed", unchanged)
    runner.main()
    assert compared == [("d" * 40 if has_candidate else "a" * 40, BUILD.source_sha)]
    assert json.loads(blobs["delivery/current.json"].value) == before
    assert blobs["delivery/operation.lock"].value is None
    assert not calls  # No image pull, Terraform plan/apply or state write.
    assert "Candidate skipped" in (tmp_path / "summary").read_text(encoding="utf-8")


def test_failed_mutation_lock_identifies_its_workflow_and_creation_time(monkeypatch, tmp_path):
    blobs, _ = setup_runner(monkeypatch, tmp_path, "apply")
    with pytest.raises(RuntimeError):
        runner.main()
    lock = json.loads(blobs["delivery/operation.lock"].value)
    assert lock["workflow_run"].endswith("/actions/runs/10/attempts/1")
    assert lock["created_at"]
    assert lock["configuration_sha"] == BUILD.source_sha


def test_image_filter_compares_retained_trees_and_detects_deletions(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "ROOT", tmp_path)

    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=tmp_path, text=True, capture_output=True, check=True
        ).stdout.strip()

    git("init")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.invalid")
    (tmp_path / "README.md").write_text("initial", encoding="utf-8")
    (tmp_path / "apps/api").mkdir(parents=True)
    api = tmp_path / "apps/api/main.py"
    api.write_text("initial", encoding="utf-8")

    def commit():
        git("add", ".")
        git("commit", "-m", "fixture")
        return git("rev-parse", "HEAD")

    first = commit()
    (tmp_path / "README.md").write_text("docs only", encoding="utf-8")
    docs = commit()
    assert not runner.image_inputs_changed(first, docs)
    api.write_text("new behavior", encoding="utf-8")
    application = commit()
    assert runner.image_inputs_changed(docs, application)
    (tmp_path / "README.md").write_text("more docs", encoding="utf-8")
    later = commit()
    assert not runner.image_inputs_changed(application, later)
    assert runner.image_inputs_changed(first, later)  # Cumulative delta from retained revision.
    api.unlink()
    assert runner.image_inputs_changed(later, commit())
    with pytest.raises(runner.CommandFailure):
        runner.image_inputs_changed("f" * 40, later)  # Missing history must fail closed.

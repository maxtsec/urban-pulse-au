"""Guard the publication trust boundary and protected-branch check interface."""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[2]


def workflow(name):
    # BaseLoader preserves YAML keys such as 'on' and treats values as data only.
    return yaml.load((ROOT / f".github/workflows/{name}.yml").read_text(), Loader=yaml.BaseLoader)


def test_only_main_push_can_reach_the_publisher():
    data = workflow("images")
    assert data["on"] == {"push": {"branches": ["main"]}}
    publish = data["jobs"]["publish"]
    assert publish["needs"] == "verify"
    assert publish["if"] == (
        "github.event_name == 'push' && github.ref == 'refs/heads/main' && "
        "github.repository == 'maxtsec/urban-pulse-au'"
    )
    assert data["jobs"]["verify"]["uses"] == "./.github/workflows/check.yml"
    assert "if" not in data["jobs"]["manifest"]
    assert data["jobs"]["manifest"]["needs"] == "publish"


def test_ci_still_reports_the_three_required_pr_check_names():
    checks = workflow("check")
    assert "pull_request" in checks["on"]
    assert "workflow_call" in checks["on"]
    assert checks["on"]["push"]["branches-ignore"] == ["main"]
    assert set(checks["jobs"]) == {"checks", "terraform", "compose"}
    for name, job in checks["jobs"].items():
        assert job.get("name", name) == name
    assert checks["permissions"] == {"contents": "read"}


def test_only_publish_job_requests_oidc_and_authentication_follows_build_and_smoke():
    data = workflow("images")
    assert data["permissions"] == {"contents": "read"}
    for name, job in data["jobs"].items():
        expected = (
            {"contents": "read", "id-token": "write"} if name == "publish" else {"contents": "read"}
        )
        assert job["permissions"] == expected
    steps = data["jobs"]["publish"]["steps"]
    build = next(
        i for i, s in enumerate(steps) if s.get("uses", "").startswith("docker/build-push-action@")
    )
    smoke = next(i for i, s in enumerate(steps) if "publication smoke" in s.get("run", ""))
    auth = next(
        i
        for i, s in enumerate(steps)
        if s.get("uses", "").startswith("google-github-actions/auth@")
    )
    push = next(i for i, s in enumerate(steps) if s.get("run", "").startswith("docker push"))
    assert build < smoke < auth < push
    assert steps[build]["with"]["push"] == "false"
    assert steps[auth]["with"]["create_credentials_file"] == "false"
    assert "credentials_json" not in steps[auth]["with"]
    assert steps[auth]["with"]["access_token_lifetime"] == "900s"


@pytest.mark.parametrize("name", ["images", "check"])
def test_actions_are_pinned_in_publishing_and_its_verification_gate(name):
    for job in workflow(name)["jobs"].values():
        for step in job.get("steps", []):
            if "uses" in step:
                assert re.fullmatch(r"[\w-]+/[\w-]+@[0-9a-f]{40}", step["uses"])
                if name == "images" and step["uses"].startswith("actions/checkout@"):
                    assert step["with"]["persist-credentials"] == "false"


def test_build_bases_are_pinned_but_named_stages_and_scratch_are_allowed():
    for path in ["apps/api/Dockerfile", "apps/web/Dockerfile"]:
        stages = {"scratch"}
        for line in (ROOT / path).read_text().splitlines():
            if not line.startswith("FROM "):
                continue
            parts = line.split()
            if parts[1] not in stages:
                assert re.fullmatch(r"[^\s]+@sha256:[0-9a-f]{64}", parts[1])
            if len(parts) == 4:
                stages.add(parts[3])


def test_artifacts_upload_only_explicit_publication_records_in_hidden_work_directory():
    for job in workflow("images")["jobs"].values():
        for step in job.get("steps", []):
            if step.get("uses", "").startswith("actions/upload-artifact@"):
                options = step["with"]
                assert options["include-hidden-files"] == "true"
                assert options["if-no-files-found"] == "error"
                assert options["path"].startswith(".local/image-publication/")
                assert options["path"].endswith(".json")
                assert "*" not in options["path"]

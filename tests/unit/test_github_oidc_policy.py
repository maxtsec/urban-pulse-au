"""The image-builder federation policy admits only main-branch pushes of one workflow."""

import json
import re
from pathlib import Path

import pytest

POLICY = json.loads(
    (Path(__file__).parents[2] / "infra/bootstrap/github-oidc-policy.json").read_text(
        encoding="utf-8"
    )
)
WORKFLOW = "maxtsec/urban-pulse-au/.github/workflows/images.yml"


def claims(**overrides: str) -> dict[str, str]:
    """A main-branch push token for the image workflow, per GitHub's OIDC claim set."""
    token = {
        "repository_id": "1404249334",
        "repository_owner_id": "98444048",
        "event_name": "push",
        "ref": "refs/heads/main",
        "workflow_ref": f"{WORKFLOW}@refs/heads/main",
    }
    return token | overrides


def builder_allowed(token: dict[str, str]) -> bool:
    # Terraform joins each section into `assertion.<claim> == '<value>'` terms with &&:
    # the provider condition gates every token, then the builder mapping must be true.
    return all(token.get(claim) == value for claim, value in POLICY["provider"].items()) and all(
        token.get(claim) == value for claim, value in POLICY["image_builder"].items()
    )


def test_main_push_of_image_workflow_is_allowed():
    assert builder_allowed(claims())


@pytest.mark.parametrize(
    "token",
    [
        # A pull request runs on its merge ref.
        claims(event_name="pull_request", ref="refs/pull/7/merge"),
        # pull_request_target reports the base branch ref, so ref alone cannot exclude it.
        claims(event_name="pull_request_target"),
        claims(event_name="workflow_dispatch"),
        claims(event_name="schedule"),
        claims(ref="refs/heads/feature", workflow_ref=f"{WORKFLOW}@refs/heads/feature"),
        claims(ref="refs/tags/v1.0.0", workflow_ref=f"{WORKFLOW}@refs/tags/v1.0.0"),
        # Another workflow on main cannot borrow the builder identity.
        claims(workflow_ref="maxtsec/urban-pulse-au/.github/workflows/check.yml@refs/heads/main"),
        # Forks and lookalike repositories carry different numeric IDs.
        claims(repository_id="999"),
        claims(repository_owner_id="999"),
    ],
)
def test_other_events_refs_workflows_and_repositories_are_denied(token):
    assert not builder_allowed(token)


def test_policy_values_are_safe_cel_string_literals():
    for section in ("provider", "image_builder"):
        for claim, value in POLICY[section].items():
            assert re.fullmatch(r"[a-z_]+", claim)
            assert "'" not in value and "\\" not in value


def test_builder_is_bound_to_one_push_workflow_on_its_ref():
    builder = POLICY["image_builder"]
    assert builder["event_name"] == "push"
    assert builder["workflow_ref"] == f"{WORKFLOW}@{builder['ref']}"

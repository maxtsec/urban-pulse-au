"""Deployment safety cases; no provider credentials or cloud writes."""

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from scripts import demo_delivery as d
from scripts.image_publication import Build, assemble, component_record

REPO = "maxtsec/urban-pulse-au"
BUILD = Build(
    "australia-southeast2-docker.pkg.dev/example-project/urbanpulse", REPO, "b" * 40, "123", "1"
)
MANIFEST = assemble(
    BUILD,
    [
        component_record(BUILD, c, f"{BUILD.image_repository}/{c}@sha256:" + "c" * 64)
        for c in ("api", "web")
    ],
)
RUN = {
    "id": 123,
    "run_attempt": 1,
    "event": "push",
    "head_branch": "main",
    "head_repository": {"full_name": REPO},
    "repository": {"full_name": REPO},
    "path": ".github/workflows/images.yml",
    "status": "completed",
    "conclusion": "success",
    "head_sha": BUILD.source_sha,
}
INPUTS = {
    "name_prefix": "urbanpulse-demo",
    "release_id": "sha-old-r1",
    "source_sha": "a" * 40,
    "serving_revision": "urbanpulse-demo-sha-old-r1",
    "api_image": BUILD.image_repository + "/api@sha256:" + "a" * 64,
    "web_image": BUILD.image_repository + "/web@sha256:" + "a" * 64,
    "schema_revision": "0007_city_checkpoints",
    "import_id": "e" * 64,
    "project_id": "example-project",
    "runtime_secret_version": "1",
}
METADATA = {
    "schema_revision": INPUTS["schema_revision"],
    "import_id": INPUTS["import_id"],
    "migrations": "f" * 64,
}


def current():
    return {
        "schema_version": 1,
        "inputs": deepcopy(INPUTS),
        "serving": {
            "revision": INPUTS["serving_revision"],
            "inputs": deepcopy(INPUTS),
            "accepted": True,
        },
        "candidate": None,
        "previous": None,
        "in_progress": None,
    }


def service():
    return {
        "iap_enabled": True,
        "invoker_iam_disabled": False,
        "deletion_protection": True,
        "scaling": [{"max_instance_count": 2}],
        "labels": {"source-sha": "a" * 40},
        "terraform_labels": {"source-sha": "a" * 40},
        "effective_labels": {"source-sha": "a" * 40},
        "template": [
            {
                "revision": INPUTS["serving_revision"],
                "labels": {"source-sha": "a" * 40},
                "service_account": "runtime@example-project.iam.gserviceaccount.com",
                "containers": [
                    {
                        "name": c,
                        "image": INPUTS[c + "_image"],
                        "resources": {"memory": "512Mi"},
                        "env": [{"name": "DATABASE_URL", "version": "1"}],
                    }
                    for c in ("web", "api")
                ],
            }
        ],
        "traffic": [
            {
                "type": "TRAFFIC_TARGET_ALLOCATION_TYPE_REVISION",
                "revision": INPUTS["serving_revision"],
                "percent": 100,
                "tag": "",
            }
        ],
    }


def candidate_plan():
    inputs = d.candidate_inputs(current(), MANIFEST, "d10a1")
    before = service()
    after = deepcopy(before)
    for label in ("labels", "terraform_labels", "effective_labels"):
        after[label]["source-sha"] = inputs["source_sha"]
    after["template"][0]["labels"]["source-sha"] = inputs["source_sha"]
    after["template"][0]["revision"] = inputs["name_prefix"] + "-" + inputs["release_id"]
    for c in after["template"][0]["containers"]:
        c["image"] = inputs[c["name"] + "_image"]
    after["traffic"].append(
        {
            "type": "TRAFFIC_TARGET_ALLOCATION_TYPE_REVISION",
            "revision": after["template"][0]["revision"],
            "percent": 0,
            "tag": "candidate",
        }
    )
    plan = {
        "resource_changes": [
            {
                "address": a,
                "mode": "managed",
                "change": {
                    "actions": ["update"] if a == d.SERVICE else ["no-op"],
                    "before": before if a == d.SERVICE else {},
                    "after": after if a == d.SERVICE else {},
                },
            }
            for a in sorted(d.MANAGED)
        ]
    }
    return inputs, plan


def change(plan):
    return next(r["change"] for r in plan["resource_changes"] if r["address"] == d.SERVICE)


def test_successful_publication_requires_exact_run_attempt_and_digests():
    assert d.publication(MANIFEST, RUN, REPO) == BUILD
    broken = deepcopy(MANIFEST)
    broken["images"]["web"]["reference"] = "other.example/web:latest"
    with pytest.raises(ValueError):
        d.publication(broken, RUN, REPO)


@pytest.mark.parametrize(
    "field,value",
    [
        ("event", "pull_request"),
        ("head_branch", "feature"),
        ("conclusion", "failure"),
        ("status", "in_progress"),
        ("path", ".github/workflows/other.yml"),
        ("run_attempt", 2),
        ("head_sha", "d" * 40),
        ("head_repository", {"full_name": "fork/repository"}),
    ],
)
def test_untrusted_or_stale_publication_rejected(field, value):
    with pytest.raises(ValueError):
        d.publication(MANIFEST, RUN | {field: value}, REPO)


def test_candidate_plan_keeps_serving_traffic_and_all_security_settings():
    inputs, plan = candidate_plan()
    d.validate_plan(plan, inputs, "candidate")
    assert inputs["serving_revision"] == INPUTS["serving_revision"]
    assert inputs["runtime_secret_version"] == "1"


@pytest.mark.parametrize(
    "field,value",
    [
        ("iap_enabled", False),
        ("invoker_iam_disabled", True),
        ("scaling", [{"max_instance_count": 20}]),
        ("deletion_protection", False),
    ],
)
def test_candidate_cannot_smuggle_security_or_capacity_changes(field, value):
    inputs, plan = candidate_plan()
    change(plan)["after"][field] = value
    with pytest.raises(ValueError, match="boundary"):
        d.validate_plan(plan, inputs, "candidate")


@pytest.mark.parametrize(
    "mutation",
    ["identity", "secret", "memory", "traffic", "iam", "create", "drift", "missing_state"],
)
def test_unapproved_delivery_changes_stop_before_apply(mutation):
    inputs, plan = candidate_plan()
    template = change(plan)["after"]["template"][0]
    if mutation == "identity":
        template["service_account"] = "migration@example-project.iam.gserviceaccount.com"
    if mutation == "secret":
        template["containers"][0]["env"][0]["version"] = "latest"
    if mutation == "memory":
        template["containers"][0]["resources"]["memory"] = "4Gi"
    if mutation == "traffic":
        change(plan)["after"]["traffic"][0]["percent"] = 50
    if mutation == "iam":
        next(r for r in plan["resource_changes"] if r["address"] != d.SERVICE)["change"][
            "actions"
        ] = ["update"]
    if mutation == "create":
        change(plan)["actions"] = ["create"]
    if mutation == "drift":
        plan["resource_drift"] = [{"address": d.SERVICE}]
    if mutation == "missing_state":
        plan["resource_changes"] = []
    with pytest.raises(ValueError):
        d.validate_plan(plan, inputs, "candidate")


@pytest.mark.parametrize("field", ["schema_revision", "import_id", "migrations"])
def test_identity_changes_require_separate_initialization(field):
    with pytest.raises(ValueError, match="Job workflow"):
        d.compatible(METADATA, METADATA | {field: "changed"}, INPUTS)


def test_pending_deployment_and_superseded_promotion_are_rejected():
    with pytest.raises(ValueError, match="recovery"):
        d.candidate_inputs(current() | {"in_progress": {"id": "interrupted"}}, MANIFEST, "d1a1")
    with pytest.raises(ValueError, match="superseded"):
        d.promotion_inputs(current(), "old-candidate")


def test_promotion_only_switches_traffic_and_preserves_rollback_record():
    inputs, plan = candidate_plan()
    revision = inputs["name_prefix"] + "-" + inputs["release_id"]
    c = d.advance_record(current(), inputs, {"revision": revision, "inputs": inputs}, "candidate")
    promoted = d.promotion_inputs(c, revision)
    before = deepcopy(change(plan)["after"])
    after = deepcopy(before)
    after["traffic"] = [
        {
            "type": "TRAFFIC_TARGET_ALLOCATION_TYPE_REVISION",
            "revision": revision,
            "percent": 100,
            "tag": "",
        }
    ]
    change(plan).update(before=before, after=after)
    d.validate_plan(plan, promoted, "promote")
    result = d.advance_record(c, promoted, {"revision": revision, "inputs": promoted}, "promote")
    assert result["previous"] == current()["serving"]
    assert result["candidate"] is None
    after["template"][0]["containers"][0]["image"] = "other"
    with pytest.raises(ValueError):
        d.validate_plan(plan, promoted, "promote")


def test_workflows_are_opt_in_pinned_and_promotion_is_protected():
    root = Path(__file__).resolve().parents[2]
    cd = yaml.load(
        (root / ".github/workflows/cd.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader
    )
    deploy = yaml.load(
        (root / ".github/workflows/deploy.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader
    )
    assert cd["concurrency"]["cancel-in-progress"] == "false"
    assert "workflow_run" in cd["on"] and "workflow_dispatch" in cd["on"]
    for job in cd["jobs"].values():
        assert "DEMO_CD_ENABLED" in job["if"]
        assert job["uses"] == "./.github/workflows/deploy.yml"
    assert "demo-promotion" in deploy["jobs"]["deliver"]["environment"]
    checkout = deploy["jobs"]["deliver"]["steps"][0]
    assert checkout["with"]["fetch-depth"] == "0"  # Retained source may be many commits back.
    for step in deploy["jobs"]["deliver"]["steps"]:
        if "uses" in step:
            assert len(step["uses"].split("@")[1]) == 40
    assert "create_credentials_file" in str(deploy)
    assert "upload-artifact" not in str(deploy)


def test_private_seed_preserves_accepted_serving_identity_and_rejects_pending_candidate():
    from scripts.demo_delivery_seed import seed

    inputs = INPUTS | {
        "iap_members": ["user:operator@example.org"],
        "custom_oauth_client_id": "123-example.apps.googleusercontent.com",
    }
    record = seed(inputs, "private-reviewed-acceptance")
    assert record["serving"]["revision"] == inputs["serving_revision"]
    assert record["candidate"] is None and record["in_progress"] is None
    assert record["serving"]["accepted"]
    previous = inputs | {
        "release_id": "sha-old-r0",
        "serving_revision": "urbanpulse-demo-sha-old-r0",
    }
    seeded = seed(inputs, "private-review-covers-both-revisions", previous)
    assert seeded["previous"]["revision"] == previous["serving_revision"]
    with pytest.raises(ValueError):
        seed(inputs, "private-review", previous | {"import_id": "different"})
    with pytest.raises(ValueError):
        seed(inputs | {"serving_revision": "different"}, "private-reviewed-acceptance")
    with pytest.raises(ValueError):
        seed(inputs, "")

"""Pure guards for fixture-only candidate deployment and explicit promotion."""

from copy import deepcopy
from typing import Any

from scripts.image_publication import Build, assemble, component_record

SERVICE = "google_cloud_run_v2_service.demo"
MANAGED = {
    SERVICE,
    "google_cloud_run_v2_service_iam_binding.iap_invoker",
    "google_iap_web_cloud_run_service_iam_binding.reviewers[0]",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def publication(manifest: dict[str, Any], run: dict[str, Any], repository: str) -> Build:
    require(
        run["event"] == "push"
        and run["head_branch"] == "main"
        and run["head_repository"]["full_name"] == repository
        and run["repository"]["full_name"] == repository
        and run["path"] == ".github/workflows/images.yml"
        and run["status"] == "completed"
        and run["conclusion"] == "success",
        "Only successful main image-publication runs are deployable",
    )
    build = Build(**manifest["build"])
    build.validate()
    require(
        build.source_repository == repository
        and build.source_sha == run["head_sha"]
        and build.run_id == str(run["id"])
        and build.run_attempt == str(run["run_attempt"]),
        "Publication provenance differs from the source run",
    )
    expected = assemble(
        build,
        [component_record(build, c, manifest["images"][c]["reference"]) for c in ("api", "web")],
    )
    require(manifest == expected, "Publication manifest is inconsistent")
    return build


def candidate_inputs(
    current: dict[str, Any], manifest: dict[str, Any], delivery_id: str
) -> dict[str, Any]:
    require(current.get("in_progress") is None, "Interrupted deployment requires recovery")
    result: dict[str, Any] = deepcopy(current["inputs"])
    repository = manifest["build"]["image_repository"]
    for component in ("api", "web"):
        require(
            result[f"{component}_image"].startswith(f"{repository}/{component}@sha256:"),
            "Cannot change registry or project in application delivery",
        )
        result[f"{component}_image"] = manifest["images"][component]["reference"]
    result["source_sha"] = manifest["build"]["source_sha"]
    result["release_id"] = f"sha-{result['source_sha'][:12]}-{delivery_id}"
    require(len(result["release_id"]) <= 45, "Release identifier exceeds the serving contract")
    return result


def promotion_inputs(current: dict[str, Any], revision: str) -> dict[str, Any]:
    require(current.get("in_progress") is None, "Interrupted deployment requires recovery")
    candidate = current.get("candidate")
    require(
        candidate is not None
        and candidate["revision"] == revision
        and candidate["inputs"] == current["inputs"],
        "Selected candidate was superseded or is not the retained candidate",
    )
    result: dict[str, Any] = deepcopy(current["inputs"])
    result["serving_revision"] = revision
    return result


def compatible(old: dict[str, str], new: dict[str, str], inputs: dict[str, Any]) -> None:
    require(old == new, "Schema, migrations or import changed; use the reviewed Job workflow first")
    require(
        new["schema_revision"] == inputs["schema_revision"]
        and new["import_id"] == inputs["import_id"],
        "Image identity does not match the initialized deployment record",
    )


def validate_plan(plan: dict[str, Any], inputs: dict[str, Any], operation: str) -> None:
    require(not plan.get("resource_drift"), "Remote drift requires operator review")
    resources = {r["address"]: r for r in plan["resource_changes"] if r["mode"] == "managed"}
    require(set(resources) == MANAGED, "Expected the existing serving state and both IAM bindings")
    for address, resource in resources.items():
        require(
            resource["change"]["actions"] == (["update"] if address == SERVICE else ["no-op"]),
            "Delivery must update only the existing service; IAM and creation are forbidden",
        )
    change = resources[SERVICE]["change"]
    before, after = deepcopy(change["before"]), deepcopy(change["after"])
    revision = f"{inputs['name_prefix']}-{inputs['release_id']}"
    target = inputs["serving_revision"]
    expected_traffic = [
        {
            "type": "TRAFFIC_TARGET_ALLOCATION_TYPE_REVISION",
            "revision": target,
            "percent": 100,
            "tag": "",
        }
    ]
    if operation == "candidate":
        require(target != revision, "Candidate cannot receive default traffic")
        require(
            any(t["revision"] == target and t["percent"] == 100 for t in before["traffic"]),
            "Candidate must retain the existing serving target",
        )
        expected_traffic.append(
            {
                "type": "TRAFFIC_TARGET_ALLOCATION_TYPE_REVISION",
                "revision": revision,
                "percent": 0,
                "tag": "candidate",
            }
        )
        before["template"][0]["revision"] = revision
        before["template"][0]["labels"]["source-sha"] = inputs["source_sha"]
        for container in before["template"][0]["containers"]:
            container["image"] = inputs[f"{container['name']}_image"]
        for label in ("labels", "terraform_labels", "effective_labels"):
            before[label]["source-sha"] = inputs["source_sha"]
    else:
        require(operation == "promote" and target == revision, "Invalid promotion target")
        require(before["template"][0]["revision"] == revision, "Template changed since candidate")
    before["traffic"] = sorted(expected_traffic, key=lambda t: t["revision"])
    after["traffic"] = sorted(after["traffic"], key=lambda t: t["revision"])
    # Server-computed values may become unknown after a legitimate update.
    computed = {
        "conditions",
        "create_time",
        "creator",
        "delete_time",
        "etag",
        "expire_time",
        "generation",
        "last_modifier",
        "latest_created_revision",
        "latest_ready_revision",
        "observed_generation",
        "reconciling",
        "terminal_condition",
        "traffic_statuses",
        "uid",
        "update_time",
        "uri",
        "urls",
    }
    for key in computed:
        before.pop(key, None)
        after.pop(key, None)
    require(before == after, "Plan changes exceed the approved candidate/traffic boundary")


def advance_record(
    current: dict[str, Any], inputs: dict[str, Any], release: dict[str, Any], operation: str
) -> dict[str, Any]:
    result = deepcopy(current)
    result["inputs"] = inputs
    result["in_progress"] = None
    if operation == "candidate":
        result["candidate"] = release
    else:
        result["previous"] = current["serving"]
        result["serving"] = release
        result["candidate"] = None
    return result

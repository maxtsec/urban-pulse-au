"""Opt-in managed fixture delivery; cloud writes run only in the protected workflow."""

import hashlib
import io
import json
import os
import re
import subprocess
import tempfile
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import google.auth
import httpx
from google.api_core.exceptions import PreconditionFailed
from google.auth.transport.requests import AuthorizedSession, Request
from google.cloud import storage  # type: ignore[import-untyped]

from scripts.demo_delivery import (
    advance_record,
    candidate_inputs,
    compatible,
    promotion_inputs,
    publication,
    require,
    validate_plan,
)

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "maxtsec/urban-pulse-au"
IDENTITY_CODE = """import hashlib,json,tempfile
from pathlib import Path
from alembic.config import Config
from alembic.script import ScriptDirectory
from urbanpulse.adapters.city_fixture import capture_city
from urbanpulse.adapters.city_store import import_identity
c=Config()
c.set_main_option('script_location','/app/migrations')
files=sorted(Path('/app/migrations/versions').glob('*.py'))
fingerprint=hashlib.sha256(b''.join(p.name.encode()+p.read_bytes() for p in files))
with tempfile.TemporaryDirectory() as d:
    print(json.dumps(dict(
        schema_revision=ScriptDirectory.from_config(c).get_current_head(),
        import_id=import_identity(capture_city(Path(d))),
        migrations=fingerprint.hexdigest())))
"""


def encode(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=2) + "\n"


class CommandFailure(RuntimeError):
    def __init__(self, executable: str, diagnostic: str):
        super().__init__(f"{executable} failed; inspect the private deployment record")
        self.diagnostic = diagnostic


def command(args: list[str], *, data: str | None = None, cwd: Path = ROOT) -> str:
    result = subprocess.run(
        args, input=data, capture_output=True, text=True, encoding="utf-8", cwd=cwd, timeout=900
    )
    if result.returncode:
        # Terraform/SDK diagnostics can contain identities and input values.
        raise CommandFailure(Path(args[0]).name, result.stdout + "\n" + result.stderr)
    return result.stdout


# Conservative roots copied into either image, plus build/dependency configuration.
IMAGE_INPUTS = (
    "apps",
    "workers",
    "urbanpulse",
    "migrations",
    "tests/fixtures",
    "pyproject.toml",
    "uv.lock",
    ".python-version",
    ".dockerignore",
)


def image_inputs_changed(previous_sha: str, source_sha: str) -> bool:
    for sha in (previous_sha, source_sha):
        require(bool(re.fullmatch(r"[0-9a-f]{40}", sha)), "Full image source commit required")
    return bool(
        command(
            [
                "git",
                "diff",
                "--name-only",
                "--no-renames",
                previous_sha,
                source_sha,
                "--",
                *IMAGE_INPUTS,
            ],
            cwd=ROOT,
        ).strip()
    )


class DeliveryLocked(RuntimeError):
    pass


def github(path: str) -> dict[str, Any]:
    with httpx.Client(
        headers={"Authorization": "Bearer " + os.environ["GH_TOKEN"]}, timeout=45
    ) as client:
        response = client.get(f"https://api.github.com/repos/{REPOSITORY}/{path}")
        require(response.status_code == 200, "GitHub provenance read failed")
        return cast(dict[str, Any], response.json())


def fetch_publication(run_id: str, attempt: str) -> dict[str, Any]:
    require(bool(re.fullmatch(r"[1-9][0-9]{0,19}", run_id)), "Invalid publication run")
    run = github(f"actions/runs/{run_id}")
    require(str(run["run_attempt"]) == attempt, "Source workflow attempt changed")
    artifacts = github(f"actions/runs/{run_id}/artifacts?per_page=100")
    require(artifacts["total_count"] <= 100, "Too many publication artifacts")
    name = f"images-{run['head_sha']}-{attempt}"
    matches = [a for a in artifacts["artifacts"] if a["name"] == name and not a["expired"]]
    require(
        len(matches) == 1 and matches[0]["size_in_bytes"] < 2_000_000,
        "Missing or oversized publication",
    )
    url = f"https://api.github.com/repos/{REPOSITORY}/actions/artifacts/{matches[0]['id']}/zip"
    with httpx.Client(
        headers={"Authorization": "Bearer " + os.environ["GH_TOKEN"]},
        timeout=45,
        follow_redirects=True,
    ) as client:
        response = client.get(url)
        require(
            response.status_code == 200 and len(response.content) < 2_000_000,
            "Publication download failed",
        )
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        require(archive.namelist() == ["image-publication.json"], "Unexpected publication archive")
        require(archive.infolist()[0].file_size < 64_000, "Publication is too large")
        manifest = cast(dict[str, Any], json.loads(archive.read("image-publication.json")))
    publication(manifest, run, REPOSITORY)
    return manifest


def image_metadata(image: str, sha: str) -> dict[str, str]:
    command(["docker", "pull", "--platform", "linux/amd64", image])
    inspected = json.loads(command(["docker", "image", "inspect", image]))[0]
    require(image in inspected["RepoDigests"], "Registry digest differs")
    require(
        (inspected["Os"], inspected["Architecture"]) == ("linux", "amd64"), "Wrong image platform"
    )
    labels = inspected["Config"].get("Labels") or {}
    require(
        labels.get("org.opencontainers.image.revision") == sha
        and labels.get("org.opencontainers.image.source") == f"https://github.com/{REPOSITORY}",
        "Image provenance differs",
    )
    return cast(
        dict[str, str],
        json.loads(
            command(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--network",
                    "none",
                    "--read-only",
                    "--cap-drop",
                    "ALL",
                    "--security-opt",
                    "no-new-privileges",
                    "--user",
                    "65532",
                    "--memory",
                    "512m",
                    "--cpus",
                    "1",
                    "--pids-limit",
                    "128",
                    "--tmpfs",
                    "/tmp:rw,nosuid,size=128m",
                    "--entrypoint",
                    "/app/.venv/bin/python",
                    image,
                    "-c",
                    IDENTITY_CODE,
                ]
            )
        ),
    )


def terraform(root: Path, *args: str) -> str:
    return command(["terraform", f"-chdir={root}", *args])


def plan(root: Path, work: Path, inputs: dict[str, Any], label: str) -> tuple[Path, dict[str, Any]]:
    variables = work / f"{label}.tfvars.json"
    variables.write_text(encode(inputs), encoding="utf-8")
    saved = work / f"{label}.tfplan"
    # Never stream plans with private IAP identities to the public Actions log.
    terraform(
        root,
        "plan",
        "-input=false",
        "-lock-timeout=60s",
        "-no-color",
        f"-var-file={variables}",
        f"-out={saved}",
    )
    return saved, json.loads(terraform(root, "show", "-json", str(saved)))


def read_back(session: Any, base: str, inputs: dict[str, Any], operation: str) -> None:
    # The control-plane traffic status may lag successful apply completion.
    for attempt in range(12):
        try:
            response = session.get(base, timeout=45)
            require(response.status_code == 200, "Service read-back failed")
            service = response.json()
            require(
                service.get("terminalCondition", {}).get("state") == "CONDITION_SUCCEEDED",
                "Service reconciliation incomplete",
            )
            revision = f"{inputs['name_prefix']}-{inputs['release_id']}"
            response = session.get(f"{base}/revisions/{revision}", timeout=45)
            require(response.status_code == 200, "Revision read-back failed")
            deployed = response.json()
            require(
                any(
                    c.get("type") == "Ready" and c.get("state") == "CONDITION_SUCCEEDED"
                    for c in deployed.get("conditions", [])
                ),
                "Candidate platform readiness failed",
            )
            actual = {c["name"]: c["image"] for c in deployed["containers"]}
            require(
                actual == {c: inputs[f"{c}_image"] for c in ("api", "web")},
                "Deployed digests differ",
            )
            require(
                service.get("iapEnabled") and not service.get("invokerIamDisabled", False),
                "Authentication boundary differs",
            )
            traffic = service["trafficStatuses"]
            require(
                any(
                    t["revision"].split("/")[-1] == inputs["serving_revision"]
                    and t.get("percent") == 100
                    for t in traffic
                ),
                "Serving traffic differs",
            )
            if operation == "candidate":
                require(
                    len(traffic) == 2
                    and any(
                        t["revision"].split("/")[-1] == revision
                        and t.get("percent", 0) == 0
                        and t.get("tag") == "candidate"
                        for t in traffic
                    ),
                    "Candidate traffic differs",
                )
            else:
                require(
                    len(traffic) == 1 and not traffic[0].get("tag"), "Promotion traffic differs"
                )
            return
        except ValueError:
            if attempt == 11:
                raise
            time.sleep(5)


def main() -> None:
    env = os.environ
    operation = env["DELIVERY_OPERATION"]
    require(
        env.get("GITHUB_REPOSITORY") == REPOSITORY and env.get("GITHUB_REF") == "refs/heads/main",
        "Protected main workflow required",
    )
    require(
        (operation, env.get("GITHUB_EVENT_NAME"))
        in {("candidate", "workflow_run"), ("promote", "workflow_dispatch")},
        "Unsupported delivery trigger",
    )
    require(bool(re.fullmatch(r"[0-9a-f]{40}", env["GITHUB_SHA"])), "Full workflow commit required")
    delivery_id = f"d{env['GITHUB_RUN_ID']}a{env['GITHUB_RUN_ATTEMPT']}"
    require(
        bool(re.fullmatch(r"d[1-9][0-9]{0,19}a[1-9][0-9]{0,3}", delivery_id)),
        "Invalid delivery identity",
    )
    if operation == "promote":
        require(env.get("ACCEPTED_CANDIDATE") == "true", "Explicit candidate acceptance required")
        environment = github("environments/demo-promotion")
        require(
            any(
                rule.get("type") == "required_reviewers" and rule.get("reviewers")
                for rule in environment.get("protection_rules", [])
            ),
            "Promotion environment must require approval",
        )
    manifest = (
        fetch_publication(env["PUBLICATION_RUN"], env["PUBLICATION_ATTEMPT"])
        if operation == "candidate"
        else None
    )
    if manifest:
        require(
            manifest["build"]["source_sha"] == github("branches/main")["commit"]["sha"],
            "Publication was superseded",
        )
    credentials, project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    session = AuthorizedSession(credentials)  # type: ignore[no-untyped-call]
    bucket_name = env["DEMO_STATE_BUCKET"]
    require(
        bool(re.fullmatch(r"[a-z0-9][a-z0-9-]{2,61}[a-z0-9]", bucket_name)),
        "Invalid backend bucket",
    )
    bucket = storage.Client(project=project, credentials=credentials).bucket(bucket_name)
    pointer = bucket.blob("delivery/current.json")
    lock = bucket.blob("delivery/operation.lock")
    try:
        lock.upload_from_string(
            encode(
                {
                    "id": delivery_id,
                    "operation": operation,
                    "created_at": datetime.now(UTC).isoformat(),
                    "workflow_run": f"https://github.com/{REPOSITORY}/actions/runs/{env['GITHUB_RUN_ID']}/attempts/{env['GITHUB_RUN_ATTEMPT']}",
                    "configuration_sha": env["GITHUB_SHA"],
                }
            ),
            if_generation_match=0,
        )
    except PreconditionFailed:
        message = (
            "Delivery is locked by an existing operation. Inspect delivery/operation.lock "
            "and the runbook's pre-intent lock recovery; no automatic unlock or retry."
        )
        with Path(env["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as output:
            output.write(message + "\n")
        raise DeliveryLocked(message) from None
    lock.reload()
    lock_generation = lock.generation
    retain_lock = False
    try:
        pointer.reload()
        generation = pointer.generation
        current = json.loads(pointer.download_as_bytes(if_generation_match=generation))
        require(
            current["schema_version"] == 1 and current.get("in_progress") is None,
            "Deployment record needs recovery",
        )
        require(
            current["inputs"]["serving_revision"] == current["serving"]["revision"],
            "Serving pointer mismatch",
        )
        if manifest:
            retained = current.get("candidate") or current["serving"]
            if not image_inputs_changed(
                retained["inputs"]["source_sha"], manifest["build"]["source_sha"]
            ):
                with Path(env["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as output:
                    output.write(
                        "Candidate skipped: image input files are unchanged. "
                        "The retained candidate and serving record are unchanged.\n"
                    )
                return
        inputs = (
            candidate_inputs(current, manifest, delivery_id)
            if manifest
            else promotion_inputs(current, env["CANDIDATE_REVISION"])
        )
        require(inputs["project_id"] == env["GCP_PROJECT_ID"], "Backend project differs")
        with tempfile.TemporaryDirectory(prefix="urbanpulse-delivery-") as tmp:
            work = Path(tmp)
            # Local Docker auth is disposable; no credential is passed into a container.
            os.environ["DOCKER_CONFIG"] = str(work / "docker")
            credentials.refresh(Request())  # type: ignore[no-untyped-call]
            registry = inputs["api_image"].split("/", 1)[0]
            command(
                [
                    "docker",
                    "login",
                    registry,
                    "--username",
                    "oauth2accesstoken",
                    "--password-stdin",
                ],
                data=credentials.token,
            )
            previous = current["serving"]["inputs"]
            old_metadata = image_metadata(previous["api_image"], previous["source_sha"])
            new_metadata = image_metadata(inputs["api_image"], inputs["source_sha"])
            compatible(old_metadata, new_metadata, inputs)
            # Also require the web image's platform and source labels; no web code is executed.
            command(["docker", "pull", "--platform", "linux/amd64", inputs["web_image"]])
            web = json.loads(command(["docker", "image", "inspect", inputs["web_image"]]))[0]
            require(
                inputs["web_image"] in web["RepoDigests"]
                and web["Architecture"] == "amd64"
                and web["Os"] == "linux"
                and web["Config"]["Labels"]["org.opencontainers.image.revision"]
                == inputs["source_sha"],
                "Web image differs",
            )
            root = ROOT / "infra/demo-serving"
            (root / "backend.tf").write_text(
                'terraform {\n  backend "gcs" {}\n}\n', encoding="utf-8"
            )
            terraform(
                root,
                "init",
                "-input=false",
                "-lockfile=readonly",
                f"-backend-config=bucket={bucket_name}",
                "-backend-config=prefix=serving",
            )
            state = json.loads(terraform(root, "state", "pull"))
            require(state.get("resources"), "Serving state must be migrated before CD")
            bucket.blob(f"delivery/runs/{delivery_id}/before.tfstate").upload_from_string(
                encode(state), if_generation_match=0
            )
            _, baseline = plan(root, work, current["inputs"], "baseline")
            require(
                not baseline.get("resource_drift")
                and all(
                    r["change"]["actions"] == ["no-op"]
                    for r in baseline["resource_changes"]
                    if r["mode"] == "managed"
                ),
                "Existing deployment drift requires review",
            )
            saved, changes = plan(root, work, inputs, "deploy")
            validate_plan(changes, inputs, operation)
            if manifest:
                require(
                    manifest["build"]["source_sha"] == github("branches/main")["commit"]["sha"],
                    "Candidate superseded before apply",
                )
            bucket.blob(
                f"delivery/runs/{delivery_id}/approved-boundary.tfplan"
            ).upload_from_filename(str(saved), if_generation_match=0)
            plan_sha256 = hashlib.sha256(saved.read_bytes()).hexdigest()
            # Durable intent precedes the first cloud mutation. Failures thereafter retain the lock.
            pending = current | {
                "in_progress": {
                    "id": delivery_id,
                    "inputs": inputs,
                    "operation": operation,
                    "plan_sha256": plan_sha256,
                }
            }
            pointer.upload_from_string(encode(pending), if_generation_match=generation)
            pointer.reload()
            generation = pointer.generation
            retain_lock = True
            terraform(root, "apply", "-input=false", "-no-color", str(saved))
            after = terraform(root, "state", "pull")
            bucket.blob(f"delivery/runs/{delivery_id}/after.tfstate").upload_from_string(
                after, if_generation_match=0
            )
            base = f"https://run.googleapis.com/v2/projects/{inputs['project_id']}/locations/australia-southeast2/services/{inputs['name_prefix']}"
            read_back(session, base, inputs, operation)
            revision = f"{inputs['name_prefix']}-{inputs['release_id']}"
            release = {
                "revision": revision,
                "configuration_sha": env["GITHUB_SHA"],
                "plan_sha256": plan_sha256,
                "inputs": inputs,
                "metadata": new_metadata,
                "publication": manifest or current["candidate"]["publication"],
                "delivery_run": f"https://github.com/{REPOSITORY}/actions/runs/{env['GITHUB_RUN_ID']}",
                "recorded_at": datetime.now(UTC).isoformat(),
                "accepted": operation == "promote",
            }
            bucket.blob(f"delivery/runs/{delivery_id}/release.json").upload_from_string(
                encode(release), if_generation_match=0
            )
            pointer.upload_from_string(
                encode(advance_record(current, inputs, release, operation)),
                if_generation_match=generation,
            )
            retain_lock = False
            summary = Path(env["GITHUB_STEP_SUMMARY"])
            with summary.open("a", encoding="utf-8") as output:
                output.write(f"{operation} completed for `{inputs['source_sha']}`.\n\n")
                output.write(f"Revision: `{revision}`. Previous serving revision retained.\n\n")
                for component in ("api", "web"):
                    output.write(f"- {component}: `{inputs[f'{component}_image'].split('@')[1]}`\n")
                if operation == "candidate":
                    output.write(
                        "\nCandidate has zero default traffic. Authenticate to its tagged URL "
                        "and complete acceptance before manually dispatching promotion.\n"
                    )
    except Exception as exc:
        # Provider output stays in the private bucket, never an Actions artifact or log.
        error = {"type": type(exc).__name__, "mutation_started": retain_lock}
        if isinstance(exc, CommandFailure):
            error["diagnostic"] = exc.diagnostic
        bucket.blob(f"delivery/runs/{delivery_id}/failure.json").upload_from_string(
            encode(error), if_generation_match=0
        )
        raise
    finally:
        if not retain_lock:
            lock.delete(if_generation_match=lock_generation)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(
            f"Delivery stopped ({type(exc).__name__}). "
            "Inspect the private deployment record before retrying; "
            "no automatic rollback or lock override."
        )
        raise SystemExit(1) from None

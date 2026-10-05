"""Validate image publication inputs and record verified registry identities."""

import argparse
import json
import os
import re
import subprocess
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

COMPONENTS = frozenset({"api", "web"})
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


@dataclass(frozen=True)
class Build:
    image_repository: str
    source_repository: str
    source_sha: str
    run_id: str
    run_attempt: str

    @classmethod
    def from_environment(cls, env: Mapping[str, str]) -> "Build":
        result = cls(
            env.get("IMAGE_REPOSITORY", ""),
            env.get("GITHUB_REPOSITORY", ""),
            env.get("GITHUB_SHA", ""),
            env.get("GITHUB_RUN_ID", ""),
            env.get("GITHUB_RUN_ATTEMPT", ""),
        )
        result.validate()
        return result

    def validate(self) -> None:
        registry_parts(self.image_repository)
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", self.source_repository):
            raise ValueError("invalid source repository")
        if not re.fullmatch(r"[0-9a-f]{40}", self.source_sha):
            raise ValueError("publication requires a full source commit SHA")
        if any(
            not re.fullmatch(r"[1-9][0-9]{0,19}", value)
            for value in (self.run_id, self.run_attempt)
        ):
            raise ValueError("invalid workflow run identity")

    def tag(self, component: str) -> str:
        if component not in COMPONENTS:
            raise ValueError("unknown image component")
        return (
            f"{self.image_repository}/{component}:"
            f"sha-{self.source_sha}-run-{self.run_id}-{self.run_attempt}"
        )

    @property
    def run_url(self) -> str:
        return (
            f"https://github.com/{self.source_repository}/actions/runs/"
            f"{self.run_id}/attempts/{self.run_attempt}"
        )


def registry_parts(value: str) -> tuple[str, str]:
    match = re.fullmatch(
        r"([a-z]+-[a-z]+[0-9]-docker\.pkg\.dev)/([a-z][a-z0-9-]{4,28}[a-z0-9])/urbanpulse",
        value,
    )
    if match is None:
        raise ValueError("IMAGE_REPOSITORY must name the regional urbanpulse Artifact Registry")
    return match[1], match[2]


def config(build: Build, env: Mapping[str, str], component: str) -> dict[str, str]:
    registry, project = registry_parts(build.image_repository)
    provider = env.get("GCP_WORKLOAD_IDENTITY_PROVIDER", "")
    if not re.fullmatch(
        r"projects/[1-9][0-9]*/locations/global/workloadIdentityPools/github/providers/urban-pulse-au",
        provider,
    ):
        raise ValueError("invalid bootstrap workload identity provider")
    if env.get("GCP_BUILDER_SERVICE_ACCOUNT") != f"ci-builder@{project}.iam.gserviceaccount.com":
        raise ValueError("builder service account must match the registry project")
    return {"registry": registry, "project": project, "image_tag": build.tag(component)}


def docker(*args: str) -> str:
    return subprocess.check_output(["docker", *args], text=True).strip()


def inspect_image(tag: str) -> dict[str, Any]:
    images = json.loads(docker("image", "inspect", tag))
    if not isinstance(images, list) or len(images) != 1 or not isinstance(images[0], dict):
        raise ValueError("expected one inspectable image")
    return images[0]


def validate_image(image: dict[str, Any], build: Build) -> str:
    labels = image.get("Config", {}).get("Labels") or {}
    if labels.get("org.opencontainers.image.revision") != build.source_sha:
        raise ValueError("image revision does not match the source commit")
    if (
        labels.get("org.opencontainers.image.source")
        != f"https://github.com/{build.source_repository}"
    ):
        raise ValueError("image source does not match the source repository")
    if (image.get("Os"), image.get("Architecture")) != ("linux", "amd64"):
        raise ValueError("published images must target linux/amd64")
    identity = image.get("Id", "")
    if not isinstance(identity, str) or DIGEST.fullmatch(identity) is None:
        raise ValueError("image configuration identity is missing")
    return identity


def smoke(build: Build, component: str) -> None:
    tag = build.tag(component)
    validate_image(inspect_image(tag), build)
    if component == "api":
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--entrypoint",
                "/app/.venv/bin/python",
                tag,
                "-c",
                "import apps.api.main, workers.events.main, workers.city.main; "
                "from pathlib import Path; "
                "p = Path('/app/migrations'); "
                "p.is_dir() or exit('migrations missing')",
            ],
            check=True,
        )
    else:
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "-e",
                "API_UPSTREAM=127.0.0.1:8000",
                "--entrypoint",
                "caddy",
                tag,
                "validate",
                "--config",
                "/etc/caddy/Caddyfile",
                "--adapter",
                "caddyfile",
            ],
            check=True,
        )


def registry_reference(image: dict[str, Any], repository: str) -> str:
    refs = image.get("RepoDigests") or []
    matches = {
        ref
        for ref in refs
        if isinstance(ref, str)
        and ref.startswith(repository + "@")
        and DIGEST.fullmatch(ref.split("@", 1)[1])
    }
    if len(matches) != 1:
        raise ValueError("expected one registry manifest digest for the published repository")
    return matches.pop()


def verify_pushed_image(tag: str, build: Build) -> str:
    local = inspect_image(tag)
    local_id = validate_image(local, build)
    reference = registry_reference(local, tag.rsplit(":", 1)[0])
    # Pull the immutable registry identity, not the mutable tag or local configuration ID.
    docker("pull", "--platform", "linux/amd64", reference)
    if validate_image(inspect_image(reference), build) != local_id:
        raise ValueError("registry digest does not resolve to the tested local image")
    return reference


def component_record(build: Build, component: str, reference: str) -> dict[str, Any]:
    prefix = f"{build.image_repository}/{component}@"
    if (
        component not in COMPONENTS
        or not isinstance(reference, str)
        or not reference.startswith(prefix)
    ):
        raise ValueError("record points outside the expected image repository")
    if DIGEST.fullmatch(reference[len(prefix) :]) is None:
        raise ValueError("record requires a registry manifest digest")
    return {
        "schema_version": 1,
        "build": asdict(build),
        "run_url": build.run_url,
        "platform": "linux/amd64",
        "component": component,
        "tag": build.tag(component),
        "reference": reference,
    }


def assemble(build: Build, records: list[dict[str, Any]]) -> dict[str, Any]:
    images = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("component record must be an object")
        component = record.get("component")
        if component not in COMPONENTS or component in images:
            raise ValueError("publication requires exactly one record per component")
        expected = component_record(build, component, record.get("reference", ""))
        if record != expected:
            raise ValueError("record does not match this source, run and attempt")
        images[component] = {"tag": record["tag"], "reference": record["reference"]}
    if set(images) != COMPONENTS:
        raise ValueError("both API and web must be verified before publishing the manifest")
    return {
        "schema_version": 1,
        "build": asdict(build),
        "run_url": build.run_url,
        "platform": "linux/amd64",
        "images": images,
    }


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("config", "smoke", "record", "assemble"))
    parser.add_argument("--component", choices=sorted(COMPONENTS))
    parser.add_argument("--directory", type=Path, default=Path(".local/image-publication"))
    args = parser.parse_args()
    build = Build.from_environment(os.environ)
    if args.command == "assemble":
        paths = [args.directory / f"{component}.json" for component in sorted(COMPONENTS)]
        records = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
        manifest = assemble(build, records)
        write_json(args.directory / "image-publication.json", manifest)
        if summary_path := os.environ.get("GITHUB_STEP_SUMMARY"):
            with Path(summary_path).open("a", encoding="utf-8") as summary:
                summary.write(f"Source commit: `{build.source_sha}`\n\n")
                for component, image in sorted(manifest["images"].items()):
                    summary.write(f"- **{component}**: `{image['reference']}`\n")
        print(f"Verified API and web publication for {build.source_sha}")
        return
    if args.component is None:
        parser.error("--component is required")
    if args.command == "config":
        values = config(build, os.environ, args.component)
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
            for key, value in values.items():
                output.write(f"{key}={value}\n")
    elif args.command == "smoke":
        smoke(build, args.component)
    else:
        reference = verify_pushed_image(build.tag(args.component), build)
        write_json(
            args.directory / f"{args.component}.json",
            component_record(build, args.component, reference),
        )


if __name__ == "__main__":
    main()

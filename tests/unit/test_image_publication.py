"""Publication must retain the tested image and complete source/run identity."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from scripts import image_publication as publication

BUILD = publication.Build(
    "australia-southeast2-docker.pkg.dev/example-project/urbanpulse",
    "maxtsec/urban-pulse-au",
    "a" * 40,
    "123",
    "2",
)
PROVIDER = "projects/123/locations/global/workloadIdentityPools/github/providers/urban-pulse-au"
CONFIG_ID = "sha256:" + "c" * 64
MANIFEST_DIGEST = "sha256:" + "d" * 64


def environment() -> dict[str, str]:
    return {
        "IMAGE_REPOSITORY": BUILD.image_repository,
        "GITHUB_REPOSITORY": BUILD.source_repository,
        "GITHUB_SHA": BUILD.source_sha,
        "GITHUB_RUN_ID": BUILD.run_id,
        "GITHUB_RUN_ATTEMPT": BUILD.run_attempt,
        "GCP_WORKLOAD_IDENTITY_PROVIDER": PROVIDER,
        "GCP_BUILDER_SERVICE_ACCOUNT": "ci-builder@example-project.iam.gserviceaccount.com",
    }


def record(component: str, build: publication.Build = BUILD) -> dict:
    return publication.component_record(
        build, component, f"{build.image_repository}/{component}@{MANIFEST_DIGEST}"
    )


def inspected(component: str = "api") -> dict:
    return {
        "Id": CONFIG_ID,
        "Os": "linux",
        "Architecture": "amd64",
        "Config": {
            "Labels": {
                "org.opencontainers.image.revision": BUILD.source_sha,
                "org.opencontainers.image.source": "https://github.com/" + BUILD.source_repository,
            }
        },
        "RepoDigests": [f"{BUILD.image_repository}/{component}@{MANIFEST_DIGEST}"],
    }


def test_configuration_emits_scoped_registry_and_unique_run_tag():
    build = publication.Build.from_environment(environment())
    result = publication.config(build, environment(), "api")
    assert result["registry"] == "australia-southeast2-docker.pkg.dev"
    assert result["project"] == "example-project"
    assert result["image_tag"].endswith(f"/api:sha-{BUILD.source_sha}-run-123-2")
    assert replace(build, run_attempt="3").tag("api") != result["image_tag"]


@pytest.mark.parametrize(
    "key,value",
    [
        ("IMAGE_REPOSITORY", "evil.example/project/urbanpulse"),
        ("IMAGE_REPOSITORY", BUILD.image_repository + "\ninjected=true"),
        ("GITHUB_SHA", "a" * 7),
        ("GITHUB_RUN_ID", "0"),
        ("GITHUB_RUN_ATTEMPT", "2; command"),
        ("GITHUB_REPOSITORY", "../../another-repo"),
    ],
)
def test_invalid_or_injected_build_identity_is_rejected(key, value):
    with pytest.raises(ValueError):
        publication.Build.from_environment(environment() | {key: value})


@pytest.mark.parametrize(
    "overrides",
    [
        {"GCP_BUILDER_SERVICE_ACCOUNT": "ci-builder@other-project.iam.gserviceaccount.com"},
        {"GCP_WORKLOAD_IDENTITY_PROVIDER": PROVIDER + "\ninjected=true"},
        {"GCP_WORKLOAD_IDENTITY_PROVIDER": ""},
    ],
)
def test_missing_or_mismatched_bootstrap_configuration_is_rejected(overrides):
    with pytest.raises(ValueError):
        publication.config(BUILD, environment() | overrides, "api")


def test_registry_manifest_identity_cannot_fall_back_to_local_configuration_id():
    image = inspected()
    image["RepoDigests"] = []
    with pytest.raises(ValueError, match="registry manifest"):
        publication.registry_reference(image, BUILD.image_repository + "/api")


@pytest.mark.parametrize(
    "refs",
    [
        ["other.example/api@" + MANIFEST_DIGEST],
        [BUILD.image_repository + "/api@sha256:short"],
        [
            BUILD.image_repository + "/api@" + MANIFEST_DIGEST,
            BUILD.image_repository + "/api@sha256:" + "e" * 64,
        ],
    ],
)
def test_foreign_invalid_or_ambiguous_registry_digests_are_rejected(refs):
    image = inspected()
    image["RepoDigests"] = refs
    with pytest.raises(ValueError):
        publication.registry_reference(image, BUILD.image_repository + "/api")


def test_registry_readback_uses_immutable_digest_and_matches_tested_content(monkeypatch):
    reference = record("api")["reference"]
    calls = []

    def docker(*args):
        calls.append(args)
        return json.dumps([inspected()]) if args[:2] == ("image", "inspect") else "pulled"

    monkeypatch.setattr(publication, "docker", docker)
    assert publication.verify_pushed_image(BUILD.tag("api"), BUILD) == reference
    assert ("pull", "--platform", "linux/amd64", reference) in calls
    assert calls[-1] == ("image", "inspect", reference)


def test_registry_readback_rejects_different_content_even_with_matching_labels(monkeypatch):
    def docker(*args):
        image = inspected()
        if args[-1] != BUILD.tag("api"):
            image["Id"] = "sha256:" + "e" * 64
        return json.dumps([image]) if args[:2] == ("image", "inspect") else "pulled"

    monkeypatch.setattr(publication, "docker", docker)
    with pytest.raises(ValueError, match="tested local image"):
        publication.verify_pushed_image(BUILD.tag("api"), BUILD)


@pytest.mark.parametrize(
    "change",
    [
        {"Architecture": "arm64"},
        {"Os": "windows"},
        {"Config": {"Labels": {"org.opencontainers.image.revision": "b" * 40}}},
    ],
)
def test_unexpected_platform_or_source_cannot_be_published(change):
    with pytest.raises(ValueError):
        publication.validate_image(inspected() | change, BUILD)


def test_manifest_requires_both_components_and_retains_registry_references():
    result = publication.assemble(BUILD, [record("web"), record("api")])
    assert set(result["images"]) == {"api", "web"}
    assert result["images"]["api"]["reference"].endswith("@" + MANIFEST_DIGEST)
    assert result["build"]["source_sha"] == BUILD.source_sha
    assert result["run_url"].endswith("/runs/123/attempts/2")


@pytest.mark.parametrize("records", [[], [record("api")], [record("api"), record("api")]])
def test_partial_or_duplicate_publication_has_no_complete_manifest(records):
    with pytest.raises(ValueError):
        publication.assemble(BUILD, records)


@pytest.mark.parametrize(
    "other",
    [
        replace(BUILD, source_sha="b" * 40),
        replace(BUILD, run_id="124"),
        replace(BUILD, run_attempt="1"),
    ],
)
def test_records_from_another_commit_run_or_attempt_cannot_be_mixed(other):
    with pytest.raises(ValueError, match="source, run and attempt"):
        publication.assemble(BUILD, [record("api"), record("web", other)])


@pytest.mark.parametrize(
    "reference",
    [
        "other.example/api@" + MANIFEST_DIGEST,
        BUILD.image_repository + "/api:latest",
        None,
    ],
)
def test_record_requires_expected_component_and_digest(reference):
    with pytest.raises(ValueError):
        publication.component_record(BUILD, "api", reference)


def test_manifest_output_is_deterministic_and_round_trips(tmp_path: Path):
    target = tmp_path / "nested" / "images.json"
    value = publication.assemble(BUILD, [record("api"), record("web")])
    publication.write_json(target, value)
    first = target.read_bytes()
    publication.write_json(target, publication.assemble(BUILD, [record("web"), record("api")]))
    assert target.read_bytes() == first
    assert json.loads(first) == value


def test_assembly_appends_both_immutable_references_to_run_summary(tmp_path, monkeypatch):
    summary = tmp_path / "summary.md"
    summary.write_text("Existing summary\n", encoding="utf-8")
    directory = tmp_path / "records"
    web = publication.component_record(
        BUILD, "web", f"{BUILD.image_repository}/web@sha256:" + "e" * 64
    )
    for component, value in [("api", record("api")), ("web", web)]:
        publication.write_json(directory / f"{component}.json", value)
    for name, value in environment().items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setattr("sys.argv", ["publication", "assemble", "--directory", str(directory)])
    publication.main()
    output = summary.read_text(encoding="utf-8")
    assert output.startswith("Existing summary\n")
    assert BUILD.source_sha in output
    assert record("api")["reference"] in output
    assert web["reference"] in output
    assert CONFIG_ID not in output
    assert json.loads((directory / "image-publication.json").read_text()) == publication.assemble(
        BUILD, [record("api"), web]
    )


def test_invalid_assembly_does_not_write_a_success_summary(tmp_path, monkeypatch):
    summary = tmp_path / "summary.md"
    for component in ["api", "web"]:
        build = BUILD if component == "api" else replace(BUILD, run_attempt="1")
        publication.write_json(tmp_path / f"{component}.json", record(component, build))
    for name, value in environment().items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setattr("sys.argv", ["publication", "assemble", "--directory", str(tmp_path)])
    with pytest.raises(ValueError, match="source, run and attempt"):
        publication.main()
    assert not summary.exists()
    assert not (tmp_path / "image-publication.json").exists()

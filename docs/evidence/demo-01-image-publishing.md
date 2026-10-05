# DEMO-01 image publishing verification

Date: 6 October 2026. Scope: publishing implementation based on main `9bbf12086f34e445a262035177cd67c28a149357`, with the working changes in this PR. These local builds are rehearsals, not published release images. Operations: [image publishing runbook](../runbooks/image-publishing.md). Progress: [delivery plan](../delivery-plan.md).

## Local verification

| Check | Result |
| --- | --- |
| Ruff lint/format and application mypy | Passed |
| Strict mypy for the publication helper | Passed |
| Unit suite | 491 passed, including record validation, immutable registry identity, workflow permissions/triggers, pinned dependencies and existing OIDC claim-policy cases |
| Actionlint 1.7.12, pinned container | Passed for both workflows |
| API/runtime and web/serving builds | Both pinned Linux amd64 targets built; source/platform labels verified; API imports/migration directory and Caddy configuration passed |
| Local registry readback | Both images pushed to an isolated registry; the helper pulled each registry manifest digest and confirmed the same image configuration and source labels as the tested local image |
| Compiled serving smoke under Python `-O` | 38 Chromium tests passed; same-origin routing, CSP, three-domain replay and API/database outage/recovery passed; containers, networks and recorded volumes removed |
| Repository configuration | Three non-secret Actions variables populated from existing Terraform outputs; no IAM or cloud resource changes |

The registry rehearsal used `registry:3@sha256:ddf754342cfc8acc51a56d5d0ab6af06826461864460636d8bd5c546dab2a7b8`, bound to Docker's internal loopback. The Windows host-loopback attempt could not be reached by Docker's daemon; the successful rehearsal used daemon-loopback. It verified `verify_pushed_image` against real registry responses, including the distinction between manifest digest and local configuration ID. The temporary registry and its anonymous volume were removed. No image was pushed to GCP during this rehearsal.

Reproduce the credential-free checks from the repository root:

```powershell
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked mypy scripts/image_publication.py
uv run --locked pytest -q tests/unit
uv run --locked python -O -m scripts.web_serving_smoke
```

Run the pinned actionlint command in `check.yml` with the repository mounted read-only. For container identity checks, build both workflow targets with its platform, provenance setting and OCI labels; run the helper's `smoke` command using the same build identity. An isolated local registry can exercise `verify_pushed_image`; it does not exercise Google federation. Local logs and readback references are under ignored `.local/image-publication-rehearsal/` and `.local/web-serving-smoke/`.

## Live acceptance boundary

The first authorized main push must establish actual GitHub-to-GCP federation, Artifact Registry writes/readback and the complete two-image artifact. Record that exact SHA, run URL and image digests here after it succeeds. A PR run cannot establish this positive case because the current builder trust intentionally excludes its claims.

Existing policy tests cover denied PR, pull-request-target, fork, branch, workflow and dispatch claims. Actual denied impersonation evidence remains outstanding; use the [bounded verification procedure](../runbooks/image-publishing.md#first-live-verification). Static checks and a local registry are not live IAM evidence. Hosted deployment, IAP, migration jobs and revision rollback retain their separate ADR 0010 acceptance cases.

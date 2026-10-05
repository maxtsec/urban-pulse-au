# Image publishing

Decision: [ADR 0010](../adr/0010-hosted-fixture-demo.md). Progress: [delivery plan](../delivery-plan.md). Verification: [publication evidence](../evidence/demo-01-image-publishing.md).

## Configure the existing bootstrap

Set these repository **Actions variables**, using the outputs from `terraform -chdir=infra/bootstrap output`. They are identifiers, not credentials.

| Actions variable | Terraform output |
| --- | --- |
| `GCP_IMAGE_REPOSITORY` | `image_repository` |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | `workload_identity_provider` |
| `GCP_BUILDER_SERVICE_ACCOUNT` | `builder_service_account` |

Keep the [bootstrap trust restrictions](gcp-bootstrap.md#trust-boundary). Do not add a service-account key or broaden the accepted workflow/event to test a feature branch. Configuration is validated before building.

## Main publication flow

1. A push to `main` starts [`images.yml`](../../.github/workflows/images.yml). Its `verify` job calls [`check.yml`](../../.github/workflows/check.yml) at the same commit and waits for all three jobs: application checks, Terraform validation and Compose/browser smoke. Branch pushes and PRs still run `check.yml` directly with the protected check names `checks`, `terraform`, `compose`; main uses the reusable invocation instead of a duplicate standalone CI run.
2. Build the API `runtime` and web `serving` targets for `linux/amd64`, with pinned base images and source SHA/repository labels. Validate the built API imports/migrations and Caddy configuration before authenticating. The full Compose/browser checks are the preceding source-commit gate; these per-image checks are an additional packaging check.
3. Exchange GitHub OIDC for a short-lived builder access token, then log into the regional registry. Only the publishing job requests `id-token: write`. No credentials file is generated. The builder retains repository-scoped image write permissions, with no deployer or runtime-secret role.
4. Push each tested local image. Read its registry manifest digest, pull that immutable reference, and verify that its platform, source labels and image configuration identity match the tested image. A local image configuration ID alone cannot become a deployment reference.
5. Assemble a publication record only when both components have verified records from the same source commit, workflow run and attempt. Save it as `image-publication.json` in the `images-<full-sha>-<attempt>` Actions artifact, and append the source SHA and both immutable image references to the run summary.

Tags have the form `sha-<full-sha>-run-<run-id>-<attempt>`. They make individual attempts identifiable; consumers must use the recorded `repository@sha256:...` references. There is no mutable `latest` tag and no Git release tag. A successful publication does not deploy Cloud Run, execute migrations or promote traffic.

The publication record includes the full source SHA, source repository, run/attempt URL, target platform and both image tags/digests. It is the image portion of a future deployment record, not proof of hosted acceptance. Actions retains these artifacts for 90 days. The run summary also exposes the digests without downloading an artifact; it is tied to the workflow run and is not a permanent deployment archive. Before deploying, retain the chosen record with the environment, schema/configuration versions and last verified rollback target as required by the [release policy](../delivery-plan.md#release-policy); do not rely on an expiring CI artifact as the long-term rollback record.

## Failure and recovery

- Failed verification, configuration or container checks stop publication. Failed authentication stops the registry write; fix configuration or the reviewed bootstrap instead of adding a key.
- One component can be pushed before the other fails. Such an attempt has no complete publication artifact and must not be selected for deployment.
- Use **Re-run all jobs** to retry publication. Records from different attempts are deliberately rejected; re-running only failed jobs cannot combine an earlier successful component with the new attempt.
- A failed push/readback/record assembly must not change any serving revision or previous deployment record. Deployment is a separate workflow.
- Base-image and action updates require a reviewed commit, renewed workflow/container checks and a new publication record. Never change the digest referenced by a retained deployment.

## First live verification

After merging, open the main push's Publish images run. Confirm its verification jobs passed for that exact SHA, both publishing jobs succeeded, and its manifest contains two registry references. Independently pull those references from Artifact Registry and record the run URL, source SHA and digests in the evidence document. This is the first positive federation proof; local registry rehearsal and policy tests do not establish it.

The bootstrap acceptance also requires actual rejected impersonation attempts from `pull_request` and `pull_request_target` contexts. Do not enable publishing for these events. A separately reviewed bounded denial probe must never check out or execute PR code, publish an image or disclose its OIDC/access token; record the rejected operation and claim context. Until that evidence exists, describe negative federation coverage as policy tests only.

References: [Google GitHub authentication action](https://github.com/google-github-actions/auth), [Docker build action](https://github.com/docker/build-push-action), [reusable workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows).

# Google Cloud identity bootstrap

Decision: [ADR 0010](../adr/0010-hosted-fixture-demo.md). Progress: [delivery plan](../delivery-plan.md).

[`infra/bootstrap`](../../infra/bootstrap) prepares the identities that later DEMO-01 workflows use. It enables the bootstrap APIs, adopts the existing Artifact Registry Docker repository, creates a GitHub OIDC Workload Identity pool and provider, and creates the `ci-builder` service account. It creates no Cloud Run service, Cloud SQL instance, IAP setting, secret, deployer/runtime identity or service-account key.

The bootstrap operator runs it with their own Google account. CI never runs `plan` or `apply` for this configuration; CI only checks formatting and validates the configuration without credentials.

## Trust boundary

| Element | Restriction |
| --- | --- |
| Federation provider | Accepts only tokens whose numeric GitHub repository and owner IDs match this repository. Forks and renamed lookalike repositories are rejected. |
| `ci-builder` impersonation | Only a `push` event running `.github/workflows/images.yml` from `refs/heads/main`. `pull_request`, `pull_request_target` (which reports the base `refs/heads/main` ref), `workflow_dispatch`, schedules, tags, other branches and other workflows are denied. |
| `ci-builder` permissions | `roles/artifactregistry.writer` on the `urbanpulse` repository only. No deployment, IAM, Secret Manager or project-wide roles. |
| Credentials | Short-lived federated tokens only. Do not create or download service-account keys. |

The claim values live in [`github-oidc-policy.json`](../../infra/bootstrap/github-oidc-policy.json). Terraform turns each section into exact-match CEL: the `provider` section becomes the provider's attribute condition, and the `image_builder` section sets the `attribute.image_builder` mapping to `allowed` only when every claim matches. The builder binding trusts only `attribute.image_builder/allowed`. [Policy tests](../../tests/unit/test_github_oidc_policy.py) evaluate the same file against push, pull-request, pull-request-target, dispatch, branch, tag, workflow and repository variants. Change the workflow file name or allowed event only by editing that file and its tests together.

Anyone who can push to `main`, or merge a change to the image workflow, can publish images. The branch rules below protect that publication boundary. Configure and operate the workflow using the [image publishing runbook](image-publishing.md). Deployment remains a separate identity and workflow, added in a later reviewed change.

## Main branch rules

Read-only verified on 6 October 2026: repository ruleset [main, ID 24537367](https://github.com/maxtsec/urban-pulse-au/rules/24537367) is **active**, targets `~DEFAULT_BRANCH` (currently `main`) with no exclusions, and has no bypass actors.

| Rule | Enforced setting |
| --- | --- |
| Pull requests | Required; allowed merge method is rebase only |
| Required approvals | 0 in GitHub configuration; this does not imply that a PR has been reviewed |
| History | Linear history; force pushes and branch deletion blocked |
| Required checks | Exact contexts **`checks`**, **`terraform`**, **`compose`**, from GitHub Actions (integration ID `15368`) |
| Up-to-date requirement | Strict: the PR branch must be up to date before the required checks permit merging |

Branch and PR runs report the three contexts directly. On main, the image workflow reuses these jobs as its verification gate; the run can display a caller prefix. All three contexts are jobs in [`check.yml`](../../.github/workflows/check.yml). Treat their job/display names as an interface with this ruleset. Before renaming or removing one, coordinate the ruleset change, confirm the replacement context actually runs on the PR head, and retain the old context until the transition is ready. A successful differently named job does not satisfy an old required name; a skipped workflow can leave the required check pending.

To diagnose a blocked PR, compare its head's check contexts/results with the active ruleset and the effective rules returned by `GET /repos/maxtsec/urban-pulse-au/rules/branches/main`. Record deliberate ruleset changes here. This verification establishes branch enforcement only; successful and denied federated publishing still need the image-workflow acceptance described below.

## Apply

Prerequisites: the project already exists with billing and budget alerts, and you are signed in with `gcloud`. In PowerShell, use `gcloud.cmd` if script execution is disabled.

1. Create application-default credentials for Terraform and bill API quota to the project:

   ```powershell
   gcloud.cmd auth application-default login
   gcloud.cmd auth application-default set-quota-project <project-id>
   ```

2. Create the ignored variables file from the repository root:

   ```powershell
   Copy-Item infra/bootstrap/terraform.tfvars.example infra/bootstrap/terraform.tfvars
   ```

   Set `project_id` to the project ID, not its display name. Check it with `gcloud.cmd projects list`.

3. Initialize and review the plan:

   ```powershell
   terraform -chdir=infra/bootstrap init -lockfile=readonly
   terraform -chdir=infra/bootstrap plan "-out=bootstrap.tfplan"
   ```

   Expect one import (the `urbanpulse` repository), API enablement entries, one pool, one provider, one service account and two IAM members. **Stop if the plan replaces or destroys the repository**, or changes resources you did not expect; report the plan output instead of applying.

4. Apply the reviewed plan, then read the outputs:

   ```powershell
   terraform -chdir=infra/bootstrap apply bootstrap.tfplan
   terraform -chdir=infra/bootstrap output
   ```

The outputs (provider name, builder email, image path and project number) are not secrets. The image workflow uses them as plain configuration.

## State and lifecycle

State is local at `infra/bootstrap/terraform.tfstate` and ignored by Git. It holds resource identifiers, not credentials, but it is the only record linking these resources to Terraform: keep timestamped private backups outside disposable worktrees before and after each apply (including partial failure), verify their hashes and retain the previous copy. Moving state to a Cloud Storage backend is a later change once the project has a state bucket.

Do not commit `terraform.tfvars`, plan files or state. Both roots commit Linux AMD64, Windows AMD64 and macOS ARM64/AMD64 checksums and use `-lockfile=readonly` for normal initialization and CI. For intentional provider updates, follow the [multi-platform lock refresh](demo-foundation.md#validate-without-credentials) and review both lock-file diffs.

Workload Identity pools and providers are soft-deleted for 30 days after deletion. During that window the same IDs cannot be recreated, so do not destroy them to "reset" the configuration; undelete or rename instead. Destroying this configuration does not disable the APIs.

## Verify

After applying, these read-only checks confirm the boundary. Every command names the project explicitly, so the result does not depend on the active `gcloud` configuration. Replace `<project-id>` with the `project_id` in `terraform.tfvars` and `<region>` with the Terraform `region` (default `australia-southeast2`).

```powershell
gcloud.cmd iam workload-identity-pools providers describe urban-pulse-au --project=<project-id> --location=global --workload-identity-pool=github --format="yaml(attributeCondition,attributeMapping)"
gcloud.cmd iam service-accounts get-iam-policy ci-builder@<project-id>.iam.gserviceaccount.com --project=<project-id>
gcloud.cmd artifacts repositories get-iam-policy urbanpulse --project=<project-id> --location=<region>
gcloud.cmd iam service-accounts keys list --iam-account=ci-builder@<project-id>.iam.gserviceaccount.com --project=<project-id> --managed-by=user
```

Expect the condition to name the numeric repository and owner IDs, and `attribute.image_builder` to require `push`, `refs/heads/main` and the `images.yml` workflow. The only `workloadIdentityUser` member should end in `/attribute.image_builder/allowed`, the repository should grant only `artifactregistry.writer` to `ci-builder`, and the key list should be empty. A successful federated publish from a `main` push, and rejected attempts from `pull_request` and `pull_request_target` runs, remain acceptance work described in the [publishing verification procedure](image-publishing.md#first-live-verification). Static policy checks alone do not establish these live outcomes.

## Serving IAP prerequisite

Before the separate serving root is planned, establish the IAP API and service identity through a reviewed bootstrap step. API enablement alone is not identity-creation evidence. With the correct project selected explicitly and approval for this setup, ensure the identity using `gcloud beta services identity create --service=iap.googleapis.com --project=PROJECT_ID`; retain the returned service identity privately and verify its required Google-managed service-agent role. This step does not grant reviewer access or deploy a service.

Do not use ordinary project service-account `describe`/listing as proof that the IAP service agent is absent. Serving derives `service-PROJECT_NUMBER@gcp-sa-iap.iam.gserviceaccount.com` from the project number and grants only that principal invocation access at the service. See the [serving prerequisites](managed-demo-serving.md#preconditions-and-private-inputs) for ancestry/inherited IAM review and the separately approved custom OAuth setup. The service is created without reviewer access before OAuth is configured; a later saved plan enables only the named acceptance operator. This procedure does not change the image builder's Terraform root or identity.

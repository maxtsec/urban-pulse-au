# Managed demo foundation

Decisions: [ADR 0012](../adr/0012-managed-demo-resource-profile.md). Controls and deployment gates: [resource plan](../architecture/demo-cloud-resource-plan.md). Progress: [delivery plan](../delivery-plan.md).

## Contents and ownership

`infra/demo-foundation` is separate from the existing `infra/bootstrap` state. It defines 22 resources: four API-enablement entries, one SQL instance, one application database, four service identities, four connector grants, four secret containers and four secret-level reader grants. It owns no registry, federation provider, image-builder role, secret value, SQL login, Cloud Run service/Job, reviewer access or scheduler.

The APIs remain enabled when their resources leave state. Instance protection is enforced through both Terraform and the Cloud SQL API; secret deletion protection and database `ABANDON` are deliberate. Never clear these flags or discard state to resolve a failing plan.

## Validate without credentials

Use Terraform 1.16 or later and the committed provider lock file:

```powershell
terraform fmt -check -recursive infra
terraform -chdir=infra/demo-foundation init -backend=false -input=false -lockfile=readonly
terraform -chdir=infra/demo-foundation validate
terraform -chdir=infra/demo-foundation test
```

Both roots lock provider checksums for Linux AMD64, Windows AMD64, macOS ARM64 and macOS AMD64. Normal initialization, including CI, uses `-lockfile=readonly`. When intentionally updating a provider, refresh both roots and review their lock-file diffs:

```powershell
terraform -chdir=infra/demo-foundation providers lock -platform=linux_amd64 -platform=windows_amd64 -platform=darwin_arm64 -platform=darwin_amd64
terraform -chdir=infra/bootstrap providers lock -platform=linux_amd64 -platform=windows_amd64 -platform=darwin_arm64 -platform=darwin_amd64
```

All test runs use the mocked Google provider and `command = plan`. They test planned settings and bindings, not real IAM authorization, resource availability, backup restore, IAP login or Cloud SQL performance. CI runs these checks in its existing `terraform` job and has no apply credentials.

## Prepare a real plan

After local validation, copy `terraform.tfvars.example` to ignored `terraform.tfvars` and name the existing approved project. Keep the stable resource prefix once provisioned. Use the bootstrap operator's application-default credentials; do not create service-account keys. Inspect the current project for existing names/resources before planning; import deliberately instead of creating duplicates.

```powershell
terraform -chdir=infra/demo-foundation plan "-out=foundation.tfplan"
terraform -chdir=infra/demo-foundation show foundation.tfplan
```

If the Cloud SQL API is disabled, an instance lookup cannot prove that the planned name is unused. Obtain separate approval for prerequisite API enablement, then list the project's SQL instances and check the exact planned name **before** applying the database-creation plan. Stop on any collision; review adoption or a different name rather than replacing an existing instance. Refresh and present the full saved plan after this check; earlier approval or an earlier saved plan does not cover the refreshed plan.

Expect only the 22 scoped resources above in a fresh environment. Already-enabled APIs may be adopted according to the inspected state. Stop for any unexpected replace/delete, bootstrap-resource change, public SQL allowlist, additional IAM grant or credential value. Present the saved plan output for architect review. Only after explicit approval, apply that exact file with `terraform -chdir=infra/demo-foundation apply foundation.tfplan`; never run a bare `apply` that calculates a different plan. If configuration or remote state changes, generate a new saved plan and obtain review again.

State and plan files are ignored and local. Before each apply, back up any existing `infra/demo-foundation/terraform.tfstate` to a timestamped private location outside the disposable worktree. After apply, including a partially failed apply, back up the resulting state again. Verify the copied file's hash matches the source and retain the previous backup; do not rely solely on Terraform's rolling `.backup` file. No foundation state exists before its first apply. Migration to a remote backend is separate work. Empty secret-container metadata is not a secret value, but future resources can make state sensitive. Never commit state, plans, private tfvars or database credentials.

## Post-apply checks before deployment

- Read back tier/region/version, connector enforcement, encrypted access, absent authorized networks, both deletion protections, disk size and backup/PITR configuration. Check remaining disk space before importing.
- Verify four distinct identities, project-scoped connector access and one-to-one secret access; confirm they have no image-write, deployer, IAM-administration or unrelated-secret roles.
- As the private bootstrap operator, enable PostGIS, create least-privilege non-superuser SQL login roles and apply the [role connection caps](../architecture/demo-cloud-resource-plan.md#connection-envelope). Verify grants and denied operations using each role. Create secret values only through the private secret procedure, then reference numbered versions.
- Record actual connection/reserved settings and baseline usage. Run managed PostGIS compatibility and backup restore checks. Cloud SQL shared-core has no SLA; backup settings alone do not prove recoverability.
- Complete the API pooling and bounded Job-runner gates before adding serving or Job resources. Use `terraform output deployment_contract` for the target limits; it does not configure an application, enforce role caps or serialize executions.
- Configure explicit organization-only IAP access in the serving step. A project organization or account-domain string alone is not evidence that an audience restriction has been tested.

No command in this runbook grants deployment approval or executes an application Job. First candidate deployment and promotion follow ADR 0010 after these prerequisites pass.

# Managed fixture serving

Decisions: [ADR 0010](../adr/0010-hosted-fixture-demo.md), [ADR 0012](../adr/0012-managed-demo-resource-profile.md). Progress: [delivery plan](../delivery-plan.md). The [serving root](../../infra/demo-serving) owns one Cloud Run service and two service-scoped IAM role bindings. Foundation owns SQL, runtime identity and secrets; [Jobs](managed-demo-jobs.md) own explicit initialization/processing. No migrations run at API startup. This root does not create a load balancer, scheduler or deployment workflow.

## Runtime boundary

Caddy is the only ingress container, port 8080, and proxies to the API on localhost:8000. The API declares no ingress port; listening on all instance interfaces supports its own platform probes without adding a separate public API endpoint. Caddy starts after the API startup probe succeeds. API and web share one runtime identity; only the API receives the numbered database URL and socket mount, but both containers share the identity's permissions. This is packaging separation, not a credential security boundary against a compromised sidecar.

Both containers use startup `/health/ready` and liveness `/health/live` on their own ports. Startup allows 24 attempts at five-second intervals; liveness uses three attempts at 30-second intervals. Each probe has a four-second timeout. Database/pool exhaustion must produce readiness 503 without changing liveness to a database check. Request timeout is 60 seconds; Caddy retains its 30-second upstream response-header limit. The API binds `0.0.0.0:8000` for platform probe reachability and runs one Uvicorn process, pool size two, zero overflow and the existing one-second checkout wait.

Service and revision bounds are min zero/max two, concurrency four, request-based CPU allocation, no startup CPU boost. Initial per-container limits are one vCPU/512 MiB each (two vCPU/1 GiB combined per instance). Both use the documented [second-generation memory minimum](https://docs.cloud.google.com/run/docs/configuring/services/memory-limits). These are implementation starting values for the actual plan review and managed measurement, not sizing evidence. Job memory measurements do not establish serving memory needs. Enforce the [connection envelope](../architecture/demo-cloud-resource-plan.md#connection-envelope), including overlapping revisions, role caps and replacement allowance.

## Preconditions and private inputs

1. Verify the project's full organization ancestry (including any intermediate folders) and the actual users/groups belong to it. `organization_domain` constrains configuration syntax only; it does not prove domain ownership, group membership or identity eligibility. Google-managed IAP OAuth is the accepted organization-only profile. Projects without an organization fail the resource precondition. External access/custom OAuth requires a new decision.
2. Verify `run.googleapis.com`, `iap.googleapis.com` and the foundation connector/secret APIs are enabled. IAP API enablement/service-agent creation is a separately reviewed setup step. If retained bootstrap evidence does not establish its service identity, obtain approval before the idempotent ensure-identity step using `gcloud beta services identity create --service=iap.googleapis.com --project=PROJECT_ID`. The root derives its documented email from the project number; it deliberately does not use `google_service_account` or ordinary project service-account listing as an existence test. Retain the reviewed Service Usage identity-creation response as bootstrap evidence. Verify its required Google-managed service-agent role; never grant this role to an application/user identity.
3. Check service name availability. Do not adopt an existing unmanaged service implicitly. Review inherited project/folder/organization IAM: service-scoped bindings cannot remove inherited invoker or IAP accessor grants. Stop if inherited access broadens the intended audience. These role bindings are authoritative at this service, so review existing grants before updating an existing deployment.
4. Verify successful publication, exact commit CI, both manifest digests, `linux/amd64`, API revision label and compiled web target. Save the publication record outside expiring workflow artifacts. Preserve the same source SHA across the pair; Terraform validates references but cannot prove image provenance.
5. Verify the initialized schema, active import, worker completion, runtime SQL caps/read-only privileges and enabled numbered secret version against the pinned images. The `schema_revision` and `import_id` inputs are deployment-record assertions, not runtime enforcement: the API reads the currently selected import. Do not change that pointer concurrently with acceptance. Neither GET nor this Terraform root initializes data.
6. Copy [example values](../../infra/demo-serving/terraform.tfvars.example) into ignored `terraform.tfvars`. Use the four distinct foundation identities/secrets, but attach only runtime. Set a unique `release_id` for every changed image or revision configuration; retain previous revision records. Keep actual account/group names, plans and state private. `iap_members` is intentionally not marked sensitive: review every added/removed principal in the saved plan, and never publish that plan or its output.

The apply operator needs reviewed service deployment and service-scoped IAM permissions plus act-as on runtime, and read access to project/ancestry metadata. This root grants none of those operator permissions and changes no builder/deployer identity. Do not solve a permission failure by adding a broad project role.

## Plan and first deployment

```powershell
terraform -chdir=infra/demo-serving init -backend=false -input=false -lockfile=readonly
terraform -chdir=infra/demo-serving validate
terraform -chdir=infra/demo-serving test
terraform -chdir=infra/demo-serving plan "-out=serving.tfplan"
terraform -chdir=infra/demo-serving show -no-color serving.tfplan
```

First plan: three resources to add, no changes/deletions: service, IAP-agent invoker binding, reviewer accessor binding. Data-source reads are not resources to create. Review real names, images, source, resources, socket/identity/secret version and audience. Record the plan/variable hashes. An isolated mocked plan is not a real cloud plan or approval.

For the first service there is no older revision: explicitly set `serving_revision` to `name_prefix-release_id`. It receives 100% of the default URL traffic, protected by IAP. Limit `iap_members` to the named acceptance operators until all gates pass; do not pretend the first service has a zero-traffic baseline. After acceptance, review the audience expansion separately.

Before and after apply, back up any local state to the existing private backup location, verify SHA-256 and retain the prior copy. Record explicitly when no pre-apply state exists. Apply only the reviewed saved file, after architect approval:

```powershell
terraform -chdir=infra/demo-serving apply serving.tfplan
```

Inspect real service settings, IAM and both image digests afterwards, and confirm a fresh plan has no changes. No creation/apply/execution command belongs in validation CI. Definition deletion is protected; decommissioning needs its own review.

## Candidate, promotion and rollback

| Operation | Inputs and expected plan |
| --- | --- |
| Deploy candidate | New image/source pair and unique `release_id`; keep `serving_revision` unchanged. Old verified revision keeps 100%; new revision gets a `candidate` tag and zero default traffic. |
| Promote | Keep candidate template/image/settings unchanged; explicitly set `serving_revision` to its name. Review a traffic change to 100% and removal of the temporary candidate target. |
| Roll back | Keep current template pins unchanged; set only `serving_revision` to the last verified compatible revision. The current candidate remains tagged with zero default traffic. No image rebuild, SQL downgrade or import deletion. |

Every step uses a newly saved/reviewed plan. Never use an implicit LATEST target or `ignore_changes` on traffic. Zero traffic means zero default-route allocation: authenticated requests to the candidate tag can still start instances and use database connections. Restrict the allowlist throughout acceptance. First-deployment recovery has no older verified revision; close access and repair through review rather than inventing a rollback target.

Before promotion/rollback, describe the target revision and compare both actual image digests, source SHA, runtime secret version, schema/import compatibility and health evidence with its retained deployment record. Terraform validates the revision name, not its existence or compatibility. The `candidate_release` output describes the current template only; it must not be reported as the serving release while an older revision receives traffic. Keep candidate, serving and previous verified rollback records distinct.

## Acceptance before reviewer access

| Case | Evidence |
| --- | --- |
| IAP boundary | Actual IAP enabled, invoker check enabled, only IAP agent has service invoker; anonymous/unlisted/external identities denied on default and candidate URLs, plus any future domain. No public binding. A login redirect alone is not an authorized-user success test. |
| Named operator | Organization user can open compiled UI, city at 0/180/360, all three domain panels, geometry and capture evidence; missing/stale/outage scenarios preserve their meanings. |
| Data and health | Runtime role reads only; API startup succeeds only with usable PostGIS; liveness survives pool saturation and dependency outage without a restart caused by database checks. Verify both container probes in the actual revision. |
| Capacity | Real shared-core/socket path at concurrency four, cold and warm sample counts, p95, pool waits/timeouts, 503 rate, container memory and role sessions; retain the accepted connection envelope. Review one/two/three-second checkout waits only if measured contention justifies it. |
| Operational readiness | Cloud Logging captures request/container failures; authenticated uptime and storage/failure alerts verified before ongoing reviewer use. No health bypass around IAP for monitoring. |
| Recovery | Separate-target restore and Job cancellation/deadline/overlap rehearsals complete; candidate failure leaves the verified traffic target intact; compatible traffic rollback restores the known city output without rewriting retained history. |

Cloud Run probe/traffic/IAP behavior requires a managed rehearsal, including both API probes and dependent web startup on the first candidate; local shared-network tests do not prove platform probing. Local saturation and compiled-serving tests cover application behavior; mocked Terraform tests cover declared topology and rejection cases. They do not establish hosted auth, replacement behavior, performance or recovery. No serving acceptance or automatic CD is claimed by this PR.

References: [direct IAP and organization prerequisites](https://docs.cloud.google.com/run/docs/securing/identity-aware-proxy-cloud-run), [pinned Cloud Run provider schema](https://github.com/hashicorp/terraform-provider-google/blob/v7.46.1/website/docs/r/cloud_run_v2_service.html.markdown), [Cloud Run service IAP IAM](https://github.com/hashicorp/terraform-provider-google/blob/v7.46.1/website/docs/r/iap_web_cloud_run_service_iam.html.markdown).

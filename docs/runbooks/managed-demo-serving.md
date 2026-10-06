# Managed fixture serving

Decisions: [ADR 0010](../adr/0010-hosted-fixture-demo.md), [ADR 0012](../adr/0012-managed-demo-resource-profile.md) and [ADR 0013](../adr/0013-named-consumer-iap-access.md). Progress: [delivery plan](../delivery-plan.md). The [serving root](../../infra/demo-serving) owns one Cloud Run service, its IAP-agent invoker binding and, after OAuth bootstrap, a conditional service-scoped reviewer binding. Foundation owns SQL, runtime identity and secrets; [Jobs](managed-demo-jobs.md) own explicit initialization/processing. No migrations run at API startup. This root does not create a load balancer, scheduler or deployment workflow.

## Runtime boundary

Caddy is the only ingress container, port 8080, and proxies to the API on localhost:8000. The API declares no ingress port; listening on all instance interfaces supports its own platform probes without adding a separate public API endpoint. Caddy starts after the API startup probe succeeds. API and web share one runtime identity; only the API receives the numbered database URL and socket mount, but both containers share the identity's permissions. This is packaging separation, not a credential security boundary against a compromised sidecar.

Both containers use startup `/health/ready` and liveness `/health/live` on their own ports. Startup allows 24 attempts at five-second intervals; liveness uses three attempts at 30-second intervals. Each probe has a four-second timeout. Database/pool exhaustion must produce readiness 503 without changing liveness to a database check. Request timeout is 60 seconds; Caddy retains its 30-second upstream response-header limit. The API binds `0.0.0.0:8000` for platform probe reachability and runs one Uvicorn process, pool size two, zero overflow and the existing one-second checkout wait.

Service and revision bounds are min zero/max two, concurrency four, request-based CPU allocation, no startup CPU boost. Initial per-container limits are one vCPU/512 MiB each (two vCPU/1 GiB combined per instance). Both use the documented [second-generation memory minimum](https://docs.cloud.google.com/run/docs/configuring/services/memory-limits). These are implementation starting values for the actual plan review and managed measurement, not sizing evidence. Job memory measurements do not establish serving memory needs. Enforce the [connection envelope](../architecture/demo-cloud-resource-plan.md#connection-envelope), including overlapping revisions, role caps and replacement allowance.

## Preconditions and private inputs

1. Use a custom Web OAuth client with an External consent audience for the named consumer acceptance operator. Project organization membership and email-domain matching do not establish eligibility or access. First bootstrap uses `iap_members = []` and `custom_oauth_client_id = null`; follow the [OAuth stage](#custom-oauth-bootstrap-and-operator-access) before granting access. Complete the [domain-restricted-sharing gate](#domain-restricted-sharing-gate) before first apply and before configuring OAuth. Inspect full ancestry for inherited IAM; do not relax an organization policy silently.
2. Verify `run.googleapis.com`, `iap.googleapis.com` and the foundation connector/secret APIs are enabled. IAP API enablement/service-agent creation is a separately reviewed setup step. If retained bootstrap evidence does not establish its service identity, obtain approval before the idempotent ensure-identity step using `gcloud beta services identity create --service=iap.googleapis.com --project=PROJECT_ID`. The root derives its documented email from the project number; it deliberately does not use `google_service_account` or ordinary project service-account listing as an existence test. Retain the reviewed Service Usage identity-creation response as bootstrap evidence. Verify its required Google-managed service-agent role; never grant this role to an application/user identity.
3. Check service name availability. Do not adopt an existing unmanaged service implicitly. Review inherited project/folder/organization IAM: service-scoped bindings cannot remove inherited invoker or IAP accessor grants. Stop if inherited access broadens the intended audience. These role bindings are authoritative at this service, so review existing grants before updating an existing deployment.
4. Verify successful publication, exact commit CI, both manifest digests, `linux/amd64`, API revision label and compiled web target. Save the publication record outside expiring workflow artifacts. Preserve the same source SHA across the pair; Terraform validates references but cannot prove image provenance.
5. Verify the initialized schema, active import, worker completion, runtime SQL caps/read-only privileges and enabled numbered secret version against the pinned images. The `schema_revision` and `import_id` inputs are deployment-record assertions, not runtime enforcement: the API reads the currently selected import. Do not change that pointer concurrently with acceptance. Neither GET nor this Terraform root initializes data.
6. Copy [example values](../../infra/demo-serving/terraform.tfvars.example) into ignored `terraform.tfvars`. Use the four distinct foundation identities/secrets, but attach only runtime. Set a unique `release_id` for every changed image or revision configuration; retain previous revision records. Keep actual account/group names, plans and state private. `iap_members` is intentionally not marked sensitive: review every added/removed principal in the saved plan, and never publish that plan or its output.

The apply operator needs reviewed service deployment and service-scoped IAM permissions plus act-as on runtime, and read access to project/ancestry metadata. This root grants none of those operator permissions and changes no builder/deployer identity. Do not solve a permission failure by adding a broad project role.

## Domain-restricted-sharing gate

Verify that a **new** IAP grant to the named consumer account is allowed before first serving apply or any OAuth setup. An existing project `roles/owner` grant does not prove this: domain-restricted sharing can reject new policy changes without removing existing grants. A successful Terraform plan also does not prove that IAM will accept the grant.

Use **IAM & Admin → Organization Policies** in the Cloud Console, select the organization, and find **Domain restricted sharing / Allowed policy member domains** (`iam.allowedPolicyMemberDomains`). Then inspect the target project's **effective** policy, including inherited folder/organization rules and project overrides. Also check `iam.managed.allowedPolicyMembers` and any custom domain-restriction constraints affecting IAM allow policies. Do not infer the project's result solely from the organization-level row. New organizations can enforce the legacy constraint by default; verify the actual settings. [Domain restriction behavior](https://docs.cloud.google.com/organization-policy/domain-restricted-sharing), [policy configuration](https://docs.cloud.google.com/organization-policy/restrict-domains).

If the Organization Policy API (`orgpolicy.googleapis.com`) is disabled and CLI reads fail, use the Console's read-only policy view. If the Console also requires API enablement or the effective settings cannot be read, record the gate as **unverified** and stop. Do not click Enable or grant additional permissions as part of this check; API enablement is a separate cloud change requiring approval.

| Verified outcome | Next action |
| --- | --- |
| Effective policies permit the intended new principal grant | Retain private evidence and continue the reviewed serving/OAuth sequence. This is eligibility evidence, not a successful IAP login test. |
| Effective restriction blocks the consumer account | Stop before OAuth setup or reviewer-access apply. Ask the architect to choose the access/policy approach. |
| API disabled, permission denied, inheritance unresolved or result otherwise unknown | Stop; neither an unreadable policy nor an absent project override means unrestricted access. Obtain approval for any necessary API/permission change before retrying. |

Retain the check time, target project/ancestry, constraint IDs, effective rules and their origin, and the result for the intended principal privately. Recheck immediately before the reviewer-access plan/apply, including if policies or ancestry changed during setup. If an exception is chosen, record it in an ADR with project scope, affected IAM grants, rollback and review conditions before preparing a separate policy change for approval. A project exception can affect grants beyond this IAP service; this PR does not authorize one.

## Plan and first deployment

```powershell
terraform -chdir=infra/demo-serving init -backend=false -input=false -lockfile=readonly
terraform -chdir=infra/demo-serving validate
terraform -chdir=infra/demo-serving test
terraform -chdir=infra/demo-serving plan "-out=serving.tfplan"
terraform -chdir=infra/demo-serving show -no-color serving.tfplan
```

First closed-bootstrap plan: **two additions, no changes/deletions**: service and IAP-agent invoker binding. There is no reviewer binding. Data-source reads are not resources to create. Review real names, images, source, resources, socket/identity/secret version and the empty audience. Record the plan/variable hashes. An isolated mocked plan is not a real cloud plan or approval.

For the first service there is no older revision: explicitly set `serving_revision` to `name_prefix-release_id`. It receives 100% of the default URL traffic, protected by IAP. Leave `iap_members` empty until the OAuth stage below. IAP blocks user access; do not pretend the first service has a zero-traffic baseline. After OAuth setup, grant only the named operator for acceptance, and review any subsequent audience expansion separately.

Before and after apply, back up any local state to the existing private backup location, verify SHA-256 and retain the prior copy. Record explicitly when no pre-apply state exists. Apply only the reviewed saved file, after architect approval:

```powershell
terraform -chdir=infra/demo-serving apply serving.tfplan
```

Inspect real service settings, IAM and both image digests afterwards, confirm no reviewer binding or inherited IAP access exists, and confirm a fresh plan has no changes. No creation/apply/execution command belongs in validation CI. Definition deletion is protected; decommissioning needs its own review.

## Custom OAuth bootstrap and operator access

Proceed only after the [domain-restricted-sharing gate](#domain-restricted-sharing-gate) has passed; an unknown or blocking policy stops this stage before creating a consent screen or client. This stage changes cloud authentication settings and requires separate approval after the closed service exists. The serving root does not own OAuth settings or its secret. Do not add a `google_iap_settings` resource or pass an OAuth secret as a Terraform variable merely to automate this step.

1. In Google Auth Platform, configure branding/contact details and select **External** audience. Review the actual testing/publication status and applicable user/verification limits; retain that status in private evidence. If test users are required, add only the acceptance operator. Do not publish the consent application for wider use as part of this step. A consent test-user entry is not an IAP grant.
2. Create a dedicated **Web application** OAuth client for this demo. Configure the documented redirect URI `https://iap.googleapis.com/v1/oauth/clientIds/CLIENT_ID:handleRedirect`, substituting its actual client ID. Use only the scopes required for IAP sign-in; do not request unrelated Google data access. See [custom OAuth setup](https://docs.cloud.google.com/iap/docs/custom-oauth-configuration).
3. Open the Cloud Run service's **Security → IAP → Configure in IAP** settings and select custom OAuth for this specific service. Enter the client ID/secret through the protected Console flow; avoid command-line arguments, terminal transcripts and downloaded credential JSON. If a copy is needed for recovery, retain it only in approved private secret storage. Record ownership and a rotation procedure: configure the replacement credential, verify login, then revoke the old one. Never grant application runtime or CI access to the OAuth secret.
4. Read back the exact service settings using the command below; compare its non-secret client ID and nonempty secret hash with the private bootstrap record. Separately inspect the consent audience, redirect URI and testing status in Google Auth Platform. Do not copy full settings/credentials into public evidence. Check inherited IAP IAM at service/project/folder/organization levels and any inherited OAuth/domain restrictions; stop if they broaden access or block the intended login.

```powershell
gcloud.cmd iap settings get --project=PROJECT_ID --resource-type=cloud-run --region=australia-southeast2 --service=urbanpulse-demo --format="json(name,accessSettings.oauthSettings.clientId,accessSettings.oauthSettings.clientSecretSha256)"
```

The [IAP settings reference](https://docs.cloud.google.com/iap/docs/reference/rest/v1/IapSettings#OAuthSettings) defines the returned client ID/hash. This read-back proves configuration only, not successful browser login. If the values are absent or differ, stop before enabling access. The Terraform input is only a recorded assertion and cannot detect OAuth drift.

5. Set `custom_oauth_client_id` to the verified ID and `iap_members` to the single approved `user:EMAIL` in ignored `terraform.tfvars`. Save a **new** plan, retain its hash, and review the actual address visibly. With unchanged service inputs, expect **one addition, no changes/deletions**: the reviewer binding. Apply that saved plan only after approval. Do not reuse the closed-bootstrap plan or change the image/revision during this access step.
6. Verify the actual IAP IAM binding and exercise the named consumer login, an unlisted account and anonymous access. Confirm the compiled UI/API work on the default URL; test the candidate-tag URL when one exists. A redirect to Google is not a successful access test. Record the sanitized results before considering this stage accepted.

Recheck OAuth settings and browser behavior for subsequent deployments and credential rotation: Terraform has no ownership of that configuration, and a no-change plan is insufficient. If access must be closed, review a plan setting `iap_members = []`; it deletes only this managed reviewer binding and leaves service/IAP intact. Verify effective access again, because inherited grants are not revoked by this operation.

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
| IAP boundary | Actual IAP enabled, invoker check enabled, only IAP agent has service invoker; anonymous and unlisted identities denied on default and candidate URLs, plus any future domain. No public binding. A login redirect alone is not an authorized-user success test. |
| Named operator | Named consumer Google user can complete custom OAuth login and open compiled UI, city at 0/180/360, all three domain panels, geometry and capture evidence; missing/stale/outage scenarios preserve their meanings. |
| Data and health | Runtime role reads only; API startup succeeds only with usable PostGIS; liveness survives pool saturation and dependency outage without a restart caused by database checks. Verify both container probes in the actual revision. |
| Capacity | Real shared-core/socket path at concurrency four, cold and warm sample counts, p95, pool waits/timeouts, 503 rate, container memory and role sessions; retain the accepted connection envelope. Review one/two/three-second checkout waits only if measured contention justifies it. |
| Operational readiness | Cloud Logging captures request/container failures; authenticated uptime and storage/failure alerts verified before ongoing reviewer use. No health bypass around IAP for monitoring. |
| Recovery | Separate-target restore and Job cancellation/deadline/overlap rehearsals complete; candidate failure leaves the verified traffic target intact; compatible traffic rollback restores the known city output without rewriting retained history. |

Cloud Run probe/traffic/IAP behavior requires a managed rehearsal, including both API probes and dependent web startup on the first candidate; local shared-network tests do not prove platform probing. Local saturation and compiled-serving tests cover application behavior; mocked Terraform tests cover declared topology and rejection cases. They do not establish hosted auth, replacement behavior, performance or recovery. No serving acceptance or automatic CD is claimed by this PR.

References: [direct IAP and custom OAuth access](https://docs.cloud.google.com/run/docs/securing/identity-aware-proxy-cloud-run), [pinned Cloud Run provider schema](https://github.com/hashicorp/terraform-provider-google/blob/v7.46.1/website/docs/r/cloud_run_v2_service.html.markdown), [Cloud Run service IAP IAM](https://github.com/hashicorp/terraform-provider-google/blob/v7.46.1/website/docs/r/iap_web_cloud_run_service_iam.html.markdown).

# ADR 0010: Hosted fixture demo and deployment identity

Date: 2026-10-05

Status: **Proposed for project architect review.** Hosting A/B, access mode and ADR 0004 acceptance remain pending; record the explicit decision and acceptance date before dependent implementation.

## Outcome and current constraints

DEMO-01 makes the existing three-domain Southbank fixture experience available through a stable HTTPS URL, with repeatable deployment and rollback. It precedes production V1 and live collection; [release policy](../delivery-plan.md#release-policy) identifies deployments by commit SHA and image digests.

The current [web image](../../apps/web/Dockerfile) runs the Vite development server. [Compose](../../compose.yaml) exposes development ports, uses a local database password and mutable dependency image tags. The API needs PostGIS, retained fixture imports and Redis readiness. City workers expose administration through CLI; they must stay private. Existing Compose tests prove local reconstruction and recovery, not Internet exposure, hosted restore or CD.

## Hosting decision

| Option | Proposed layout | Trade-off |
| --- | --- | --- |
| **A: single GCP VM (recommended)** | Docker Compose for static web/HTTPS edge, API, PostGIS, Redis and private city worker; persistent data disk; Artifact Registry for images. Propose Melbourne, subject to capacity validation. | Reuses tested service boundaries and keeps the initial resource footprint small. The project owns patching, backups and restore; one host is one failure domain. |
| B: managed serving and data services | Cloud Run serving with Cloud SQL/PostGIS, an approved Redis service and separately designed continuous worker hosting. | Reduces host administration, but adds service/network/identity boundaries and requires new integration and capacity checks. |

A is an engineering recommendation for a bounded fixture demo, not a production availability design or a sizing promise. It does not select machine size, activate a trial or authorize resource creation. [GCP container guidance](https://docs.cloud.google.com/compute/docs/containers) recommends startup scripts/cloud-init in place of the deprecated container startup agent. [Cloud Run/Cloud SQL](https://docs.cloud.google.com/sql/docs/postgres/connect-run) describes the managed alternative. [GCP region reference](https://docs.cloud.google.com/compute/docs/regions-zones) lists Melbourne as `australia-southeast2`.

For A, propose a pinned Caddy image serving the compiled SPA and proxying the API on the same origin. [Vite deployment guidance](https://vite.dev/guide/static-deploy.html) describes the static build and excludes its preview server as a production server. [Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https) provides certificate management; domain/DNS, certificate storage and network validation belong in the deployment rehearsal. This component choice is part of option A, not yet accepted.

## Option A: pull deployment and network boundary

Recommend pull delivery rather than CI-to-VM SSH. GitHub OIDC federation is restricted to the intended repository, protected main deployment workflow and environment. Separate identities have these responsibilities:

| Identity | Allowed responsibility | Excluded authority |
| --- | --- | --- |
| CI builder | Publish verified images to the designated Artifact Registry repository | Promote deployments, read runtime secrets or administer the VM |
| CI promoter | After successful CI for the exact commit, publish immutable manifests and conditionally update the demo desired-manifest pointer in a private GCS deployment bucket | SSH/IAP, VM metadata/startup-script changes, service-account attachment or runtime secret access |
| VM runtime identity | Read approved manifests/images and named secrets; publish deployment status and logs | Update desired manifests, push images or change IAM |
| Infrastructure/operator identity | Reviewed bootstrap and maintenance through IAP/OS Login; restricted monitoring setup | Used by neither normal application CI nor public containers |

A host-local systemd agent polls the desired pointer with bounded backoff, pins its object generation and reads the referenced immutable manifest. Promotion uses [GCS generation preconditions](https://docs.cloud.google.com/storage/docs/request-preconditions?hl=en) to prevent concurrent pointer updates. Agent and CI serialize deployments; persist requested, applying, failed and verified outcomes across restarts. Repeated polls must not reapply a completed generation or endlessly retry a failed migration. A rollback is an explicit new promotion referring to an earlier compatible manifest.

The agent validates environment, approved registry/repository digests, source/build identity, schema compatibility and permitted configuration references before applying a host-owned Compose template. Manifests cannot supply shell commands, arbitrary Compose files, host mounts or Docker socket access. Bootstrap owns changes to the privileged agent/template. Artifact promotion remains code-deployment authority even without SSH; record promoter identity and the immutable manifest generation. The VM writes observed status separately from desired state; publishing a pointer alone is never deployment success.

Public ingress is TCP 80/443 only: HTTP redirects to HTTPS or serves certificate validation, with no credentials sent over HTTP. SSH TCP 22 is allowed only from IAP's documented `35.235.240.0/20` range to this VM and authorized operators through OS Login; remove inherited world-open SSH rules and audit IPv6 exposure too. CI gets no tunnel/login role. API, PostgreSQL, Redis, metrics listeners and Docker administration have no public port binding. [IAP TCP forwarding guidance](https://docs.cloud.google.com/iap/docs/using-tcp-forwarding).

## Relationship to A-06, CLOUD-01 and Phase 4

A is an interim fixture-demo deployment and a reusable delivery foundation for Phase 4, not an accepted production topology. Initially it runs no live collector. The [shared-host alternative](../architecture/early-capture-options.md) remains an A-06 choice: CLOUD-01 may share the VM only after source/retention approval, measured concurrent capacity, independent restart/deployment of the collector and enforceable credential isolation. Compose service names alone do not isolate the VM's attached service-account credentials. If those conditions cannot be met, use a separate capture host. Demo deployment/rollback must not stop capture or rewrite its raw history.

CLOUD-02 adopts existing capture buckets, object identities, manifests/checkpoints, retention policy and approved identities through infrastructure state; it must not recreate history or reset the collection start date. Plan to migrate demo serving/compute where the Phase 4 design requires it, while reusing image/digest promotion, contracts, runbooks and capture resources. The deployment-manifest bucket is separate from raw-capture storage.

Revisit A before production acceptance, or earlier when measured contention affects capture/serving, independent scaling or stronger isolation is needed, or restore/recovery goals cannot be met on one host. The Phase 4 decision explicitly chooses an upgraded VM design or replacement topology such as B. Before cutover, rehearse data/queue/audit restore, transfer any collector lease/checkpoint without two active writers, compare city results and authorize the rollback window. Retire the old serving host only after verification; retain capture resources and history. Capacity, backup/retention and recovery targets are decided before provisioning, without publishing private financial figures.

## Access and fixture policy decisions

Choose password-protected reviewer access over HTTPS for the first hosted rehearsal (recommended), or anonymous read-only access after concurrent-load and request-limit checks. Keep database, Redis, worker commands and deployment controls off the public network. Credentials and provider keys do not enter images or deployment records. Public errors remain sanitized.

Explicitly accept or revise [ADR 0004](0004-southbank-fixture-map.md) before publishing its fixture map policy: stable Southbank identity, points on the boundary included with no buffer, locally rendered map without a basemap, position freshness at 120/300 seconds; service coverage has no TTL and current denotes the latest complete authored snapshot, not verified live freshness. This demo decision cannot silently approve live-source freshness or licensing.

## Secrets and minimum operational visibility

Store database and reviewer credentials in Secret Manager. The VM's attached runtime identity reads only the named, version-pinned secrets with secret-level accessor grants; use the required Compute Engine OAuth scope plus least-privilege IAM. The host agent supplies restricted runtime files mounted read-only into only the consuming service; Caddy receives a password hash. Never put secret values in images, manifests, repository files, command output or logs. Secret references/versions can be audited without the values. Rotation includes a tested coordinated database/application update, not just replacing an environment value. [Secret Manager access](https://docs.cloud.google.com/secret-manager/docs/manage-access-to-secrets), [versioned access guidance](https://docs.cloud.google.com/secret-manager/docs/create-secret-quickstart).

The fixture application needs no Google API credentials. Block its containers from the metadata credential endpoint and do not mount host credentials or a Docker socket into them; verify that denial. The host agent and Ops Agent are trusted host processes. [VM service-account guidance](https://docs.cloud.google.com/compute/docs/access/service-accounts) explains why sharing a host does not itself provide separate workload identities.

Configure Ops Agent to send host/deployment-agent logs and explicitly configured container stdout/stderr receivers to Cloud Logging, with service, environment, commit and deployment identifiers. Do not assume installing the agent automatically collects Docker logs. Exclude credentials, Authorization headers and sensitive payloads at the producer; bound local buffering/rotation and cloud retention before enabling collection. Agent health and ingestion must be tested. [Ops Agent receiver configuration](https://docs.cloud.google.com/logging/docs/agent/ops-agent/configuration).

Create an HTTPS uptime check through Caddy to `/health/ready`, validating the certificate, successful status and expected response. For protected access, use a dedicated monitoring credential permitted only on that health route, separate from the reviewer account. Keep its source secret in Secret Manager; only the restricted monitoring bootstrap may configure its authentication in Cloud Monitoring, without exposing it in logs or unprotected IaC state. The VM reads the corresponding secret for the edge verifier. Set an alert policy, an approved notification destination and a tested failure/recovery path. [Cloud Monitoring uptime checks](https://docs.cloud.google.com/monitoring/uptime-checks) support authentication but do not execute browser JavaScript: retain the authenticated city/browser deployment smoke as a separate acceptance check. No notification destination is selected by this proposal.

## Redis readiness follow-up

The current readiness endpoint requires Redis although city queries do not use it. Keep that baseline until a separate reviewed change makes cache readiness conditional on an explicit deployment setting and removes the matching Compose dependency. Test both cache-enabled failure and cache-disabled readiness, plus real city/database failure; do not claim Redis is optional by merely omitting its container. This is a candidate DEMO-01 simplification, not a runtime change in this ADR.

## Delivery sequence after acceptance

1. Package: build static web and API images, pin dependency images, separate hosted configuration from development Compose, mount Secret Manager-backed runtime credentials and label fixture mode. Verify the actual images in an isolated stack.
2. Identity: use GitHub OIDC with scoped GCP Workload Identity Federation, separate build/promoter/runtime identities, an Artifact Registry repository and a private deployment-manifest bucket. CI cannot log in to the VM. Review the exact roles, project, region, capacity and resource plan before provisioning. [Federation guidance](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines) avoids a stored service-account key.
3. Promotion: successful main-commit CI builds once, records image digests, verifies those images and promotes the desired manifest. The VM pulls and applies it, then records its observed outcome. PRs validate without deployment credentials. Infrastructure bootstrap remains separate from ordinary application deployment.
4. Rehearsal: on the VM, the agent captures the previous manifest and verified backup, stops affected workers, runs the reviewed migration/import sequence once, starts services and verifies city/health/browser behavior before marking deployment successful. Record failures without replacing the last verified rollback target.

A deployment record contains environment, full source SHA, CI/build links for that SHA, every runtime image digest, schema revision, non-secret configuration revision, secret version references, desired-object generation, observed outcome and previous verified manifest. [Artifact Registry digest pulls](https://docs.cloud.google.com/artifact-registry/docs/docker/pushing-and-pulling) identify the bytes to deploy. Record registry manifest digests rather than treating a local image configuration ID as a registry digest.

Rollback reuses the recorded images only when the schema remains compatible. Otherwise stop deployment and follow a reviewed restore or forward-fix procedure; never auto-downgrade or delete retained history. Restore rehearsal includes fixture inputs and durable delivery/audit records. Backup destination, retention and recovery expectations require acceptance before provisioning.

## Acceptance cases

- Given the normal CI identities, VM SSH/IAP, metadata changes and runtime-secret reads are denied; untrusted branches/forks cannot obtain the promotion identity. Public scans expose only 80/443 and direct SSH fails; an authorized operator can connect through IAP.
- Given a repeated, stale, malformed or unapproved manifest, the agent preserves the last verified deployment; concurrent promotion cannot overwrite a newer pointer. Restart during apply reconciles persisted state; a failed migration cannot create an endless retry loop.
- Given Secret Manager-backed credentials, only the allowed identity/service can access the named version; wrong-secret access and container metadata access fail, rotation succeeds and no secret appears in images, logs or deployment records.
- Given a unique harmless log marker from each service and the deployment agent, Cloud Logging receives the expected entries without credentials. Stopping the API causes the authenticated uptime check and alert to fail, recovery clears it, and the dedicated probe credential cannot access city data.
- Given an approved shared collector or a Phase 4 migration rehearsal, app deployment preserves collection continuity and raw identities; restore preserves checkpoints, queue/audit state and provides a verified cutover/rollback record.
- Given a clean target and a verified manifest, deployment serves the three-domain fixture map over HTTPS and exposes its commit identity; API/database/worker administration stays private.
- Given identical image digests, recreating the app uses the same artifacts without rebuilding a branch and retains the selected import and durable delivery state.
- Given a failed import, migration or city smoke check, deployment remains failed and the previous verified target stays recorded; dependency readiness alone cannot publish success.
- Given a schema-compatible prior manifest, rollback restores the observed city experience; incompatible rollback fails explicitly without deleting data.
- Given a host restart and a restored backup in a separate target, city inputs, queue state and recovery behavior are verified before access is enabled.
- Given the selected access mode, unauthorized access and concurrent requests are tested against agreed limits. Synthetic/live labels and source attribution remain visible.

Record observations and resource measurements before selecting capacity. Source access (SRC-02), continuous capture (CLOUD-01), full production telemetry and warehouse delivery remain separate work. Basic demo logging, uptime alerting and secret access are required here. This proposal contains no cloud deployment or provisioned resources.

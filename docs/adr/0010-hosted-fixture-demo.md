# ADR 0010: Hosted fixture demo and deployment identity

Date: 2026-10-05

Status: **Accepted by the project architect on 2026-10-05.** The decision selects hosting and access; implementation and resource provisioning follow the gates below.

## Decision record

| Decision | Accepted choice | Accepted on |
| --- | --- | --- |
| Hosting | **B: Cloud Run serving with Cloud SQL/PostGIS (recommended and selected)** | 2026-10-05 |
| Access | IAP; only explicitly allowed Google accounts/groups, replacing a shared reviewer password | 2026-10-05 |
| Fixture policy | Accept [ADR 0004](0004-southbank-fixture-map.md), including its service-freshness limitation | 2026-10-05 |

## Outcome and current constraints

DEMO-01 makes the three-domain Southbank fixture experience available through a stable HTTPS URL with repeatable deployment and rollback. It precedes production V1 and live collection; the [release policy](../delivery-plan.md#release-policy) identifies deployments by commit SHA and image digests.

The default [web image](../../apps/web/Dockerfile) runs Vite. [Compose](../../compose.yaml) has development ports, a local database password and mutable dependency tags. Hosted delivery needs compiled assets, pinned images, retained fixture imports and managed database connectivity. The default API mode requires Redis readiness; the [explicit no-cache mode](../development.md#run-the-fixture-demo-without-redis) supports the fixture deployment without Redis. Existing Compose tests establish local behavior; hosted identity, recovery and deployment need their own evidence.

## Hosting comparison

| Option | Layout | Engineering and operational trade-off |
| --- | --- | --- |
| A: single VM with pull deployment | Compose, static web edge, API, PostGIS, Redis and worker on a persistent host | Reuses local boundaries but owns patching, backups and one host failure domain. **Requires a custom privileged deployment agent**: manifest validation, serialized promotion, persisted apply/recovery state, migration failure handling, rollback, logging and security updates. Removing CI SSH access does not remove this implementation, testing and maintenance cost. |
| **B: managed serving and data services — Recommended; selected** | Cloud Run HTTPS serving, Cloud SQL/PostGIS, explicit private job/worker execution and optional cache only after readiness changes | Managed revisions and database operations avoid the custom host agent. Adds IAM, network, SQL compatibility and worker integration work; managed services still need capacity limits, backups and restore tests. Reuses the Phase 4 direction. |

Selection does not activate a trial or provision resources. Confirm project, region, supported Postgres/PostGIS versions, capacity, backup/recovery expectations and identities in a reviewed resource plan. Melbourne remains the preferred regional candidate. [Cloud SQL supports PostGIS](https://docs.cloud.google.com/sql/docs/postgres/extensions); verify the actual extension version against the local queries and migrations before choosing the instance.

The database/resource profile, initial organization-only audience and manual bounded worker were subsequently selected in [ADR 0012](0012-managed-demo-resource-profile.md). Its resource plan carries the connection envelope and remaining deployment gates.

## B: serving, database and workers

Serve compiled frontend assets and the API on one IAP-protected origin. The packaging candidate is a static ingress container proxying to an API sidecar over localhost in one Cloud Run revision. The [compiled serving implementation](../runbooks/web-serving.md) uses Caddy for this boundary and includes a local shared-network rehearsal; hosted acceptance remains separate. Cloud Run terminates HTTPS; the container does not manage public certificates. Both containers share the service identity and lifecycle, so grant it only application runtime permissions. Configure startup ordering/probes and keep database credentials out of static assets. [Cloud Run sidecars](https://docs.cloud.google.com/run/docs/deploying) support this layout; confirm the final packaging in the implementation PR.

Cloud SQL holds fixture inputs and durable delivery state. Use authenticated Cloud SQL connectivity with a least-privilege application database role; the migration role owns DDL separately. The resource plan must select and test private networking or authenticated connector connectivity without an unrestricted database listener. Bound connection pools, service concurrency and maximum instances together, including overlap of revisions, jobs and workers. [Cloud Run connection guidance](https://docs.cloud.google.com/sql/docs/postgres/connect-run).

Migration and fixture import run as explicit Cloud Run Jobs, never on every API startup. Durable city administration remains private. Continuous polling must not run inside a request-driven API container: worker hosting remains a separate implementation choice between bounded fixture jobs and an independently managed continuous worker. A bounded job needs a drain/termination criterion; the existing single-sweep `--once` command does not prove a run is complete. Evaluate a Cloud Run worker pool if continuous processing is required, with measured capacity and a separate identity. This ADR does not select continuous live-capture hosting.

The Redis-free demo uses an explicit cache setting and matching deployment dependencies, with tests for cache-enabled failure, cache-disabled health and real city/database failures. The default mode still requires Redis; simply omitting its container does not disable that check. Follow the [no-cache configuration](../development.md#run-the-fixture-demo-without-redis). If retained, its managed hosting/network plan needs approval before provisioning.

## IAP access and deployment identities

Enable IAP directly on the Cloud Run service, with named Google accounts/groups granted IAP access. Keep unauthenticated invocation disabled and grant the IAP service agent the required invoker role. Direct IAP protects the default URL as well as other ingress paths; a separate load balancer is not required just to enable IAP. Test default, candidate-tag and any custom-domain URLs for bypass. Bootstrap includes the supported OAuth setup for the project's organization/account configuration. [Direct IAP configuration](https://docs.cloud.google.com/run/docs/securing/identity-aware-proxy-cloud-run).

| Identity | Responsibility and boundary |
| --- | --- |
| CI builder | Publish images to the designated Artifact Registry repository; no deployment or runtime-secret access |
| CI deployer | Deploy named service/job resources and explicitly promote revisions; act as only the approved runtime/job identities; no IAM administration or direct secret reads |
| Application runtime | Connect with the application database role and read only its named secrets; no migrations, image publishing or deployment permissions |
| Migration/import job | Separate scoped identities and database roles for DDL and fixture import; no web invocation surface |
| Worker runtime | Only its database/queue and named-secret permissions; no public administration endpoint |
| Bootstrap operator | Reviewed resource, IAM, IAP and monitoring setup; not the normal application pipeline |

GitHub OIDC and Workload Identity Federation restrict deployment credentials to the intended repository, protected main workflow and deployment environment. Fork/PR workflows validate without deployment authority. Serialize deployments per environment and reject a superseded promotion. A deployer able to run code as a runtime identity has indirect access to that identity's data/secrets: protect the workflow and environment accordingly rather than treating absence of direct Secret Manager access as isolation. [Federation guidance](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines).

## Deployment flow

1. Build once from a verified full main commit SHA. Publish and test immutable image digests; record matching CI/build evidence. Retain the previous verified revision, configuration and schema compatibility record. Infrastructure bootstrap is separate from app deployment.
2. Verify resource prerequisites, named secret versions, SQL connectivity, backup/recovery readiness and compatibility with the serving revision. Use expand/contract changes when old and new revisions overlap. An incompatible schema change needs a reviewed maintenance/forward-fix or restore plan before proceeding.
3. Execute the pinned migration image as a **Cloud Run Job**, one task with parallelism one, a bounded timeout and automatic task retries disabled unless the migration is proven safe to retry. Use a database migration lock as well as CI serialization. Wait for successful execution and verify the resulting schema revision; failure leaves traffic on the previous revision and stops promotion. Starting a job is not success. [Job execution and completion](https://docs.cloud.google.com/run/docs/execute/jobs).
4. Run the explicit, idempotent fixture-import job; verify its selected import and retained city inputs without deleting existing delivery/audit history. Record job execution identifiers and exit results. Coordinate any affected workers before incompatible changes and resume only compatible versions.
5. Deploy a named candidate revision with **no traffic**, using pinned images/configuration. Test its tagged URL through IAP: authorized browser login, city/map/API, readiness, fixture attribution and version identity. On a first deployment, keep reviewer access withheld until bootstrap checks pass. A dependency health check alone cannot pass city acceptance.
6. Promote traffic explicitly to the tested revision, checking error/latency and authenticated uptime results. Record the observed serving revision and outcome before making it the last verified target. Do not use an implicit `LATEST` target or rebuild a mutable branch during promotion.
7. Rehearse rollback by directing traffic to the recorded previous compatible revision and verifying the city experience. Traffic changes are not instantaneous; allow in-flight work and verify convergence. Service rollback does **not** undo migrations, imports, job executions or worker versions. Restore/forward-fix is separately reviewed when schema compatibility is lost; never automatically downgrade or delete retained history. [Revision traffic and rollback](https://docs.cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration).

The deployment record contains environment, full source SHA, matching CI/build links, registry image digests, named service/worker revisions, migration/import job executions, schema revision, non-secret configuration revision, pinned secret references, observed outcome and previous verified deployment. Record registry manifest digests, not local image configuration IDs. [Artifact identity](https://docs.cloud.google.com/artifact-registry/docs/docker/pushing-and-pulling). A failed deployment must not replace the last verified rollback target.

## Secrets and minimum monitoring

Store database and other credentials in Secret Manager; runtime/job identities receive secret-level access only to their named, version-pinned secrets. No service-account keys, secret values or provider credentials enter images, GitHub records, logs or compiled web assets. Rotation tests coordinate database credentials and application/job revisions; retain valid rollback references for the agreed rollback window. IAP replaces the shared reviewer password. [Secret access control](https://docs.cloud.google.com/secret-manager/docs/manage-access-to-secrets).

Use Cloud Run service/job stdout/stderr collection into Cloud Logging, with environment, source SHA, revision, execution/run and correlation identifiers. Managed containers do not need a VM Ops Agent. Redact credentials, authorization headers and sensitive payloads at the producer; bound log volume and retention. Verify harmless markers from the API and each job/worker, plus migration failure and database outage diagnostics. [Cloud Run logging](https://docs.cloud.google.com/run/docs/logging).

Require an authenticated HTTPS uptime probe that validates the expected `/health/ready` response through IAP, not a login page returning success. Verify token audience and IAP programmatic authentication during implementation. If a standard Monitoring uptime checker cannot supply the selected IAP authentication, use a scheduled bounded probe job with keyless service-account signing, explicit IAP access, failure metrics and an alert policy. Its service-level IAP permission is not a health-route-only permission; no worker/admin actions are exposed on this service. Test failed authentication, API/database outage and recovery, and verify alert delivery to the approved destination. Keep authenticated browser smoke separate, since uptime checks do not run the UI. [IAP programmatic authentication](https://docs.cloud.google.com/iap/docs/authentication-howto), [uptime checks](https://docs.cloud.google.com/monitoring/uptime-checks).

## Relationship to A-06, CLOUD-01 and Phase 4

B is the managed foundation for Phase 4 serving and persistence, not an interim shared demo VM. CLOUD-02 adopts its infrastructure state, identities, artifact/deployment records and database where suitable; extend it for the remaining workers, pipelines, telemetry and production requirements. Revisit topology if measured scaling, isolation or recovery needs require it, with an explicit cutover/rollback plan before replacement.

A-06 remains open for continuous capture region, host, retention and capacity. The [shared-host alternative](../architecture/early-capture-options.md) is not selected by this demo decision. Request-driven serving is not a reliable continuous capture scheduler. CLOUD-01 requires source-use/retention approval and an independently restartable collector identity/lifecycle. App deployment and rollback must preserve capture continuity.

CLOUD-02 adopts existing raw buckets, object identities, manifests/checkpoints, retention policy and approved identities; it must not recreate raw history or reset collection dates. A capture-host change must transfer leases/checkpoints without two active writers and verify retrieval and gaps. Managed hosting acceptance does not approve live source rights, freshness thresholds or production availability. Private financial figures remain outside repository records.

## Acceptance cases

| Case | Required observation |
| --- | --- |
| Clean hosted target | Pinned images plus successful migration/import jobs serve all three fixture domains over HTTPS, with source SHA, synthetic labels and attribution visible |
| Migration fails, times out or overlaps | No traffic promotion; lock/serialization prevents conflicting DDL, failure is recorded, last verified target survives, and recovery is explicit |
| Import or candidate smoke fails | No promotion or history deletion; retained inputs/delivery state remain retrievable; CI cannot equate job submission with completion |
| Compatible revision rollback | Previous pinned revision receives traffic and city results are verified; no rebuild, migration downgrade or implicit worker rollback |
| Incompatible schema or worker version | Promotion/rollback stops for the reviewed recovery plan; restoring a backup to a separate target proves inputs, queue and audit state survive |
| IAP authorization | Allowed reviewer succeeds; anonymous access cannot retrieve data, unlisted account fails, default/tag/custom URLs do not bypass IAP, and no public DB/worker/admin route exists |
| Federation and secrets | Fork/PR credentials fail, builder cannot deploy, identities cannot read unrelated secrets, and rotation preserves the defined rollback path without leaked values |
| Monitoring | Service/job log markers arrive; authenticated probe rejects login/error responses; API/database outage and recovery generate the expected alert lifecycle |
| Capacity and restart | Concurrent requests, cold starts, revision overlap and DB reconnect stay within approved instance/connection limits; city state survives service recreation |
| Worker execution | Private execution reaches its documented terminal state or reports failure; interrupted work recovers through durable claims without depending on API request CPU |
| Phase 4 adoption/capture change | Existing data and identities are adopted; app rollout preserves capture, and any collector cutover preserves leases, checkpoints and raw-object identity |

Evidence and implementation progress are maintained in the [delivery plan](../delivery-plan.md). Resource sizing, exact worker/network configuration, notification destination and provisioning remain review gates. This documentation change creates no cloud resources.

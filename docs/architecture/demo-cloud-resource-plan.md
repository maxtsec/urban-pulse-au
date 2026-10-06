# DEMO-01 managed deployment resource plan

Decisions: [ADR 0010](../adr/0010-hosted-fixture-demo.md) and [ADR 0012](../adr/0012-managed-demo-resource-profile.md), accepted on 6 October 2026. Progress: [delivery plan](../delivery-plan.md). Apply remains a separate review of the actual resource plan.

## Resources and ownership

| Component | Responsibility | Boundary |
| --- | --- | --- |
| Existing bootstrap | Artifact Registry, builder identity and GitHub provider | Reuse outputs; no replacement or builder-policy changes |
| [Demo foundation](../../infra/demo-foundation) | Regional Cloud SQL, database, runtime/migration/import/worker identities and empty secret containers | Separate Terraform root/state; no secret values, SQL users, serving revisions or job executions |
| Serving revision | Caddy ingress and API sidecar on one IAP-protected origin | Recorded image digests, verified DB roles/secret versions/import and bounded connections first |
| Migration/import Jobs | Explicit private schema upgrade and fixture initialization | Separate roles and identities; bounded locks/execution, successful completion before promotion |
| Fixture worker Job | Manually invoked durable fixture processing | One task, finite deadline, no scheduler/pool/continuous poller attached to the API |
| Deployment workflow | Candidate checks, promotion, deployment record and compatible rollback | Separate deployer identity/trust; builder never gains deploy authority |

This work does not implement builder hardening [#28](https://github.com/maxtsec/urban-pulse-au/issues/28), dependency updates [#29](https://github.com/maxtsec/urban-pulse-au/issues/29) or image retention [#30](https://github.com/maxtsec/urban-pulse-au/issues/30).

## Selected database and recovery profile

Melbourne, PostgreSQL 17, Enterprise edition, zonal `db-g1-small`, 10 GiB SSD. Shared-core and single-zone configurations have **no Cloud SQL SLA**. The documented small-instance connection default is **50**, compared with 25 for the tiny tier; the foundation explicitly retains 50. This is a connection ceiling, not a throughput or memory-capacity guarantee. [SLA](https://cloud.google.com/sql/sla), [database flags](https://docs.cloud.google.com/sql/docs/postgres/flags).

Require the managed connector for every connection, encryption and no direct-client IP allowlist. The public address does not authorize unauthenticated/direct SQL access. Backups run daily at 16:00 UTC, retain seven successful backups and seven days of PITR logs, with deletion protection at both Terraform and API layers. Database removal from state uses `ABANDON`; protected secret containers and retained backups need an explicit decommission plan. Prove restore separately.

Disk auto-growth is disabled to keep the initial footprint explicit. Check utilization before imports; add a storage alert before ongoing demo use and resize through review before headroom is exhausted. Fixed storage is a capacity limit, not protection against a full disk. The Sunday 17:00 UTC maintenance window and zonal design allow interruptions.

## Connection envelope

The foundation exports this deployment contract. The API implementation uses one process-lifetime pool shared by input reads, PostGIS and readiness: two connections, zero overflow and a one-second checkout wait. Serving configuration must still enforce one process and the instance/revision envelope below. Job pools and execution locks are separate requirements. See the [API pool evidence](../evidence/demo-01-api-pool.md).

| Consumer | Required configuration | Planned maximum connections |
| --- | --- | ---: |
| API | Max 2 instances, 1 process each, shared pool size 2, overflow 0; budget 2 revisions plus 2 replacement instances | `(2 x 2 + 2) x 1 x (2 + 0) = 12` |
| Migration | One execution/task, main transaction plus any separate lock/control session | 2 |
| Import | One execution/task, pool at most 2 plus one spatial/bootstrap connection | 3 |
| Worker | One execution/task, pool at most 2 plus one spatial connection and one execution-lock session | 4 |
| Client role caps combined | Separate non-superuser login roles, capped across all executions/instances | **21** |
| Platform reservations and operator access | Combined planning allowance; verify actual reserved settings and baseline use | **10** |
| Unallocated headroom | `50 - 21 - 10` | **19** |

Keep Cloud Run min instances at 0, service and revision max at 2, request concurrency at 4 and one Uvicorn process. Runtime work must put **all API database access, including PostGIS and health checks, through that one bounded pool**, with finite checkout waits and controlled unavailable responses. Do not simply set one engine's pool size or multiply workers without revisiting the calculation.

### Probe wiring and checkout tuning

The serving deployment must configure the API **startup probe as `/health/ready`** and **liveness probe as `/health/live`**. Liveness must not depend on database/cache access. Never use `/health/ready` for liveness: an exhausted shared pool returns 503 under load without implying a stuck process. Deployment tests must hold both pool slots, observe readiness 503 and liveness 200, and verify that the running instance is not restarted because of that saturation. Verify the actual deployed probe configuration, including the API sidecar, before promotion.

The current one-second checkout wait is an initial value, not a measured managed-service optimum. Before candidate promotion, run the real Cloud SQL shared-core/managed-socket path at **concurrency 4**, including cold and warm requests and a mixed city/boundary/evidence/readiness workload. Record sample count, request p95, pool-wait distribution/timeouts, 503 rate and active database sessions. If connection contention causes avoidable 503s, compare one second with **two and three seconds** through reviewed candidate builds/configuration, then choose and record the measured value. Keep pool size 2, overflow 0 and the existing role/instance caps unchanged: increasing the wait alone does not add sessions. Recheck request/probe deadlines and saturation recovery after tuning; do not infer managed performance from local results.

The two replacement slots are a planning allowance, **not a guaranteed Cloud Run overshoot bound**. Cloud Run may exceed max instances, and tagged candidates/old revisions can coexist. Enforce PostgreSQL login-role connection limits of runtime 12, migration 2, import 3 and worker 4; no login role may be a superuser or gain equivalent administrative membership. These caps protect shared headroom but can make excess work fail or wait; they do not guarantee every request succeeds. Bound retries, observe active connections and rehearse controlled saturation instead of increasing `max_connections`. [Cloud Run scaling behavior](https://docs.cloud.google.com/run/docs/about-instance-autoscaling).

The envelope conservatively adds all job types even though migration/import/worker operations that affect the same data must serialize. A Job's `parallelism = 1` does not prevent two separate executions. The worker needs an application/database execution lock, and deployment must reject overlapping migrations/imports. Verify each role's total connections, including lock sessions and health checks, during overlap and recovery.

Before allowing deployment, record `SHOW max_connections`, `SHOW superuser_reserved_connections`, `SHOW reserved_connections`, application role attributes/limits and `pg_stat_activity` by role. Stop if actual reserved/operator demand exceeds the 10-slot allowance or if the measured workload violates its assigned envelope. Do not assume the documented default is the live value.

## Database and secret prerequisites

The foundation grants `roles/cloudsql.client` at project scope: it permits connector access within the project, not SQL privileges or per-instance query authorization. Each of the four service identities can read only its own database-URL secret container. No image-publisher, deployer, IAM administration, broad secret-reader role or user-managed key is added. PostgreSQL privileges provide the separate application-data boundary.

Privately bootstrap non-superuser database roles: runtime reads published fixture data; import writes owned fixture inputs; worker writes its delivery/checkpoint state; migration owns application DDL. Do not run the app as the operator or a default administrative database user. Set the connection limits above, verify actual and default table/sequence privileges, and test denied cross-role writes. Secret values/passwords and user setup remain outside Terraform; create numbered secret versions before serving/jobs reference them.

Enable PostGIS explicitly in the application database as the bootstrap operator, then record `PostGIS_Full_Version()` and run the existing spatial integration cases against the managed instance. Cloud SQL's extension support does not install it or prove local/managed equivalence. [Managed PostGIS support](https://docs.cloud.google.com/sql/docs/postgres/extensions).

## Audience and worker execution

Initial IAP access is an **explicit allowlist of organization accounts/groups**, not every organization member. Use Google-managed OAuth; do not create an external client or consent screen in this stage. Keep reviewer identities in ignored private configuration and grant access only after the candidate passes database/city checks. Verify anonymous/unlisted/external accounts are denied and default/tagged URLs do not bypass IAP. [IAP guidance](https://docs.cloud.google.com/run/docs/securing/identity-aware-proxy-cloud-run).

The worker is manually triggered as a Cloud Run Job: one task, parallelism one, retries zero and a 600-second task timeout, with one active execution enforced separately. The [finite worker runner](../runbooks/city-job.md) takes an explicit fixture run/target, drains its input and result lanes, holds a session-bound execution lock and exits zero only after verified completion. Its local supervisor deadline is at most 540 seconds, leaving cleanup time within the future task limit. Failures, dead letters or deadline expiry must produce a nonzero result with redacted diagnostics. The current single-sweep `--once` is **not** a completion criterion. No scheduler, worker pool or always-on service is selected.

The [finite migration/import runners](../runbooks/initialization-jobs.md) use the same database-wide session lock and supervisor as the worker, with one physical connection each. Migration verifies the image/reviewed revision and commits schema plus grants together; import verifies staged immutable inputs before selecting them. Require their successful results before promotion. The legacy `city_store migrate` and ingestion commands do not acquire this lock and must not overlap managed Jobs. Never run migrations on API startup.

## Implementation and apply sequence

1. Review the foundation and its credential-free mocked tests. Use the [foundation runbook](../runbooks/demo-foundation.md) to prepare an actual plan; apply only after that plan is approved.
2. Bootstrap PostGIS, database roles and secret versions privately; verify backups and restore to a separate target. Check actual database settings against the connection envelope.
3. Implement and test shared API pooling, bounded migration/import/worker runners and their deployed limits. No serving/job resources exist in the foundation, so its outputs cannot accidentally deploy the current unbounded entry points.
4. Deploy an IAP-protected candidate with verified image digests, execute initialization Jobs, then test and explicitly promote it. Preserve the previous deployment, schema compatibility and retained fixture/delivery state for rollback.

Live collection and A-06 remain separate; this fixture environment is not production V1.

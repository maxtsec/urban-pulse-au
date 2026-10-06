# Managed serving configuration verification

Verified locally on 6 October 2026. This records the original organization-only implementation; [ADR 0013](../adr/0013-named-consumer-iap-access.md) and the [consumer access evidence](demo-01-consumer-iap.md) supersede its audience, ancestry gate and first-plan resource count. Scope: [serving Terraform](../../infra/demo-serving), [deployment procedure](../runbooks/managed-demo-serving.md), and [delivery status](../delivery-plan.md).

The root describes one Melbourne Cloud Run service: compiled Caddy ingress, single-process API sidecar, direct IAP, runtime-only SQL secret/socket and explicit revision traffic. It owns three resources (service and two scoped IAM role bindings) and reads project/ancestry metadata and derives the documented IAP service-agent principal. It does not enable APIs, provision identities/databases, execute Jobs, create a deploy workflow or apply itself.

Credential-free verification passed:

- Read-only multi-platform provider lock initialization and provider validation.
- 19 mocked plan cases: IAP/invoker boundaries, explicit organization users/groups, sidecar startup/probes, runtime identity/secret/socket, bounded resources and scaling, first revision, candidate without promotion, explicit promotion and compatible-target traffic rollback. Invalid images, secret aliases, traffic targets, revision suffixes, schema and public/domain/external/service-account audiences are rejected; a project without an organization fails the resource precondition, including folder-only ancestry; nested folders with an organization are accepted. Reviewer grants remain visible in the private plan.
- Ruff lint/format, mypy and 549 unit tests. The schema/access consistency test now covers both managed Jobs and serving.
- Four real local PostGIS API-pool tests using the restricted runtime role: shared two-slot saturation, readiness 503 while liveness remains 200, query rollback/reuse, disconnected-session replacement and lifespan cleanup. These do not simulate Cloud Run's probe supervisor.
- The compiled Caddy/API shared-network browser rehearsal passed all 53 Playwright checks, including the three-domain city, direct/nested URLs, API semantics and security headers. A unit guard keeps the Terraform and shared-network rehearsal entrypoints aligned. API/database outage and recovery checks also passed under `python -O`; the isolated stack containers, network and recorded volumes were removed.

The replacement `google_project`/`google_project_ancestry` data sources were exercised against the real project in an isolated data-only Terraform plan. The organization ancestor was found and the documented IAP principal derived, with no managed resources, ordinary service-account lookup or apply. Nested-folder acceptance and folder-only rejection were verified with mocked ancestry. This does not verify any prospective audience or group membership. No serving plan against real cloud resources was generated and no serving resource/IAM change was applied. All 643 local documentation targets resolved. First-deployment audience, source/digest pair and sizing still require actual plan review; image publication alone never deploys this service.

The initial Gen2 request-based allocation is one vCPU/512 MiB per container, min zero/max two and concurrency four. Local unit/plan/browser results cannot establish its managed capacity. Cloud IAP allow/deny/default/tag tests, exact revision read-back, cold/warm workload at concurrency four, authenticated uptime/alerts, no-restart saturation, restore and managed failure/rollback rehearsals remain the [runbook acceptance](../runbooks/managed-demo-serving.md#acceptance-before-reviewer-access). The previous approved [Job repeat](demo-01-managed-jobs.md#managed-telemetry-and-idempotent-repeat) supplies idempotency and cgroup evidence for Jobs only.

Architect review selected option A: the API listens on `0.0.0.0:8000` and retains its own startup/liveness probes; Caddy still proxies over localhost and remains the only declared ingress container. The shared-network rehearsal and command consistency guard use the same listener. Actual platform probe reachability and dependent web startup remain first-candidate acceptance cases.

Option A follow-up verification: Terraform validate and all 19 mocked plans, Ruff lint/format, five deployment-consistency unit tests and the full compiled-serving smoke passed again (53 browser checks, API/database outage recovery and verified cleanup). The earlier full Python suite and PostGIS pool results above were not rerun for this listener-only change.

## Managed bootstrap and Cloud SQL read-back

On 6 October 2026, the reviewed closed-bootstrap plan was applied: two additions, no changes/deletions. Both images came from source `7c60bdd4591b931086d06d6fe8041aa5a30e6353`. Read-back confirmed their manifest digests, IAP enabled, only the IAP agent in the service invoker binding, no service reviewer binding, and 100% traffic to the explicit first revision. The effective domain-policy and inherited-access preflight passed. Private state backups matched their SHA-256 hashes.

Cloud Logging recorded API startup readiness succeeding after three attempts and web readiness after two, followed by successful liveness probes for both containers. API readiness queries PostGIS through the configured runtime connection. Anonymous requests to `/`, `/health/ready` and `/api/v1/fixture` received HTTP 302 to Google sign-in; this demonstrates interception, not a completed OAuth login or an unlisted-user denial test.

The first post-apply plan found a mount-only difference:

| Evidence | `web` mount | `api` mount |
| --- | --- | --- |
| Cloud Audit Logs: original v2 `CreateService` request | None | `cloudsql` at `/cloudsql` |
| Raw Cloud Run v2 service and revision GET | `cloudsql` at `/cloudsql` | None |
| Corrected Terraform declaration | `cloudsql` at `/cloudsql` | None |

The v1 service represents the connection through its revision-level Cloud SQL annotation and lists neither container mount. The pinned [provider's v2 container decoder](https://github.com/hashicorp/terraform-provider-google/blob/v7.46.1/google/services/cloudrunv2/resource_cloud_run_v2_service.go#L2594) copies each container's returned `volumeMounts`; the raw v2 response already contains the difference. This localizes the mismatch to the API representation, rather than a Terraform-only state transformation. It does not prove the platform's internal filesystem layout or establish a rule for every container arrangement. The [Cloud SQL connection guide](https://docs.cloud.google.com/sql/docs/postgres/connect-run) describes the managed connection and Unix socket; it does not promise API-only socket isolation in this layout.

The correction matches the observed v2 representation and retains the instance, container order, API-only numbered database secret, shared runtime identity, probes and limits. No `ignore_changes`, state editing, credential grant, new revision or cloud apply was used. A refreshed real plan with the original deployment inputs returned **No changes** (detailed exit code 0); the local state hash remained unchanged. Raw request/read-back records, logs and before/after plans are retained privately.

All 24 serving mocked plans passed with a regression assertion for the observed mount representation and API-only secret injection. The new assertion also failed against the original API-mount declaration. Ruff lint/format, five deployment-consistency unit tests, tracked Terraform formatting and 656 local documentation targets passed. Full runtime/browser suites were not rerun locally for this declaration-only correction. These tests check the declaration; the real no-change plan checks the existing deployment. A fresh creation with this declaration, reordered containers or a provider upgrade still requires the runbook's managed read-back and readiness checks. Custom OAuth, named-user login, unlisted-user denial and the remaining capacity/recovery gates are tracked in the [delivery plan](../delivery-plan.md).

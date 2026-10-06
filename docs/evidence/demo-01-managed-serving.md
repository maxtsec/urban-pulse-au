# Managed serving configuration verification

Verified locally on 6 October 2026. Scope: [serving Terraform](../../infra/demo-serving), [deployment procedure](../runbooks/managed-demo-serving.md), and [delivery status](../delivery-plan.md).

The root describes one Melbourne Cloud Run service: compiled Caddy ingress, single-process API sidecar, direct IAP, runtime-only SQL secret/socket and explicit revision traffic. It owns three resources (service and two scoped IAM role bindings) and reads the existing project/IAP service agent. It does not enable APIs, provision identities/databases, execute Jobs, create a deploy workflow or apply itself.

Credential-free verification passed:

- Read-only multi-platform provider lock initialization and provider validation.
- 17 mocked plan cases: IAP/invoker boundaries, explicit organization users/groups, sidecar startup/probes, runtime identity/secret/socket, bounded resources and scaling, first revision, candidate without promotion, explicit promotion and compatible-target traffic rollback. Invalid images, secret aliases, traffic targets, revision suffixes, schema and public/domain/external/service-account audiences are rejected; a project without an organization fails the resource precondition.
- Ruff lint/format, mypy and 548 unit tests. The schema/access consistency test now covers both managed Jobs and serving.
- Four real local PostGIS API-pool tests using the restricted runtime role: shared two-slot saturation, readiness 503 while liveness remains 200, query rollback/reuse, disconnected-session replacement and lifespan cleanup. These do not simulate Cloud Run's probe supervisor.
- The compiled Caddy/API shared-network browser rehearsal passed all 53 Playwright checks, including the three-domain city, direct/nested URLs, API semantics and security headers. API/database outage and recovery checks also passed under `python -O`; the isolated stack containers, network and recorded volumes were removed.

The project organization parent was checked read-only and matched the accepted organization-hosting requirement. This does not verify any prospective audience or group membership. No serving plan against real cloud resources was generated and no serving resource/IAM change was applied. All 642 local documentation targets resolved. First-deployment audience, source/digest pair and sizing still require actual plan review; image publication alone never deploys this service.

The initial Gen2 request-based allocation is one vCPU/512 MiB per container, min zero/max two and concurrency four. Local unit/plan/browser results cannot establish its managed capacity. Cloud IAP allow/deny/default/tag tests, exact revision read-back, cold/warm workload at concurrency four, authenticated uptime/alerts, no-restart saturation, restore and managed failure/rollback rehearsals remain the [runbook acceptance](../runbooks/managed-demo-serving.md#acceptance-before-reviewer-access). The previous approved [Job repeat](demo-01-managed-jobs.md#managed-telemetry-and-idempotent-repeat) supplies idempotency and cgroup evidence for Jobs only.

# ADR 0012: Managed fixture demo resource profile

Date: 2026-10-06

Status: **Accepted by the project architect on 2026-10-06.** This supplements [ADR 0010](0010-hosted-fixture-demo.md); acceptance selects the profile and does not authorize resource apply or production release.

## Decision

| Area | Selected profile |
| --- | --- |
| Database | Melbourne (`australia-southeast2`), PostgreSQL 17, Cloud SQL Enterprise, zonal `db-g1-small`, initial 10 GiB SSD |
| Connectivity | Cloud Run managed Cloud SQL Auth Proxy through Unix sockets; public address with connector enforcement and no authorized direct-client networks |
| Recovery | Seven retained daily backups, seven days of PITR, Terraform and API instance deletion protection |
| Audience | Initially organization-only Google-managed IAP OAuth; superseded on 2026-10-06 by [ADR 0013](0013-named-consumer-iap-access.md): custom OAuth and a named consumer acceptance operator |
| Worker | Manually triggered Cloud Run Job with a finite execution deadline; no scheduler or continuously running worker for the fixture demo |

The chosen shared-core and single-zone configurations are excluded from the Cloud SQL SLA. The small machine's documented default `max_connections` is 50; the tiny alternative defaults to 25. Keep the selected limit at 50 and reserve capacity for administration, service replacement and private jobs rather than raising it to hide excess application connections. Verify the actual database settings after provisioning. [Cloud SQL SLA](https://cloud.google.com/sql/sla), [connection defaults](https://docs.cloud.google.com/sql/docs/postgres/flags).

## Consequences

This profile favors a small fixture deployment with recoverability over high availability. Daily backups and PITR do not provide automatic zone failover or establish a recovery-time guarantee. Prove restore on a separate target before relying on the backup configuration.

The [resource plan](../architecture/demo-cloud-resource-plan.md) owns the calculated connection envelope, job termination/serialization requirements and deployment gates. Cloud Run scaling limits can be exceeded during replacement or traffic surges; global database-role limits and actual connection measurements must complement per-process pools. A manual trigger is not a global execution lock.

The [foundation Terraform](../../infra/demo-foundation) defines the database, four identities and empty secret containers. Serving, job execution, SQL role bootstrap and the deployment pipeline are separate implementation steps. The foundation's exported runtime contract is a prerequisite for those steps, not proof that the current application already meets it.

Resource sizing can be revisited through review after workload measurements. Live collection still requires A-06, and audience expansion beyond the operator requires separate review under ADR 0013. Existing builder hardening, update automation and image retention issues remain deferred.

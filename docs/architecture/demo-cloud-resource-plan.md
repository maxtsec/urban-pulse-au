# DEMO-01 managed deployment resource plan

Decision basis: [ADR 0010](../adr/0010-hosted-fixture-demo.md). Progress: [delivery plan](../delivery-plan.md). This plan separates the accepted hosting design from resource choices awaiting architect selection. No resource apply is part of preparing this plan.

## Resources and ownership

| Component | Intended responsibility | Provisioning boundary |
| --- | --- | --- |
| Existing bootstrap | Artifact Registry, builder identity and GitHub provider | Adopt existing outputs; no replacement or builder-policy changes |
| Demo foundation | Regional Cloud SQL/PostGIS, database, separate runtime/migration/import identities and secret containers | New Terraform root with separate state; operator-reviewed plan before apply |
| Serving revision | Compiled Caddy ingress and API sidecar, one IAP-protected origin | Deploy recorded image digests after database, roles, secret versions and import are verified |
| Migration and import Jobs | Private, explicit schema upgrade and fixture initialization | Separate database roles and service identities; one task, bounded timeout, no automatic retries |
| Durable fixture worker | Explicit bounded administration/recovery execution | Define completion and timeout semantics before hosting; never place a poll loop inside the request-serving API |
| Deployment workflow | Candidate checks, explicit promotion, deployment record and compatible rollback | Separate deployer identity and reviewed trust; builder never gains deployment permissions |

The foundation owns no current image pointer or traffic promotion. Image records come from the [publishing workflow](../runbooks/image-publishing.md); serving and job configuration must use immutable digests. Do not implement registry cleanup, dependency update automation or builder trust hardening in this work: these remain issues [#30](https://github.com/maxtsec/urban-pulse-au/issues/30), [#29](https://github.com/maxtsec/urban-pulse-au/issues/29) and [#28](https://github.com/maxtsec/urban-pulse-au/issues/28).

## Pending resource choices

| Choice | Proposed starting point | Alternative / trade-off |
| --- | --- | --- |
| Region and database | Melbourne; PostgreSQL 17, Enterprise edition, zonal, 10 GiB SSD; `db-g1-small` shared core | `db-f1-micro` uses less memory and has less headroom; dedicated core offers more predictable capacity. None is a measured capacity result or HA guarantee. |
| SQL connectivity | Managed Cloud SQL Auth Proxy through a Unix socket; public address with connector enforcement and no authorized direct-client networks | Private IP plus VPC requires additional network resources and review. Do not enable unrestricted direct database access. |
| Recovery | Seven daily retained backups, seven days of PITR logs, Terraform and API deletion protection | Daily backups without PITR reduce retained logs but cannot recover to an arbitrary point between backups. Restore testing is required in either case. |

These choices are proposed, not accepted by merging unrelated ADRs. Terraform resources that encode them wait for the architect's selection. Storage growth limits, service concurrency/instance limits and the total database connection allowance also need an explicit resource plan before apply; shared-core capacity must be validated with the actual workload.

## Database and secret prerequisites

The API, migration and import identities are separate. Create secret containers and secret-level IAM without embedding secret values in Terraform, images, logs, variables examples or public documentation. Add database users/roles and secret versions through a reviewed private bootstrap procedure. The API database role must not own schema or write fixture inputs; import can update its owned inputs; migration owns DDL. Verify actual privileges with each role, including denied cross-role operations.

Cloud SQL extension support does not install PostGIS automatically for the application database. Record `PostGIS_Full_Version()` and verify the project's spatial queries after the bootstrap operator enables the extension. Use PostgreSQL 17 to stay aligned with local tests, and record the actual managed PostGIS version rather than inferring it from the local image tag.

Current `urbanpulse.adapters.city_store migrate` is an explicit entry point but lacks the deployment migration lock required by ADR 0010. Add and test bounded lock acquisition, failure/no-promotion behavior and schema verification in the migration Job implementation. Do not claim an ordinary successful local migration establishes hosted migration safety.

## Serving and IAP prerequisites

Use the existing compiled serving image and localhost API proxy. Apply the accepted explicit no-cache mode, startup ordering and health probes; the image includes fixture inputs and migrations, while imported domain history remains in PostgreSQL. Do not expose database, worker or administration ports.

The current project has a Google organization. Google-managed IAP OAuth supports organization users; external reviewers require the separate custom OAuth setup. Keep reviewer identities in private configuration and withhold access until the candidate's city, database and authentication checks pass. Verify anonymous/unlisted-user denial and the default and tagged URLs; readiness alone does not establish three-domain fixture acceptance.

## Review and apply sequence

1. Select the pending resource choices and produce credential-free Terraform validation and mocked plan tests. Review the exact planned creates, IAM members and deletion protections; stop for unexpected replacement of bootstrap resources.
2. Approve/apply the foundation separately. Enable PostGIS, establish database roles and privately supply pinned secret versions. Verify backup settings and restore to a separate target.
3. Implement bounded migration/import Jobs and their tests. Wait for executions to succeed and verify schema/import identity before creating a serving candidate.
4. Deploy and test an IAP-protected candidate using the verified API/web digests; then explicitly promote and rehearse compatible rollback. Preserve fixture inputs, durable delivery state and previous deployment records.

This foundation does not deploy live collection or resolve A-06. Initial fixture serving remains part of Phase 4 and is not production V1.

## Provider references

- [Cloud SQL machine types](https://docs.cloud.google.com/sql/docs/postgres/machine-series-overview)
- [Managed PostGIS support](https://docs.cloud.google.com/sql/docs/postgres/extensions)
- [Cloud Run SQL connectivity](https://docs.cloud.google.com/sql/docs/postgres/connect-run)
- [Cloud SQL PITR configuration](https://docs.cloud.google.com/sql/docs/postgres/backup-recovery/configure-pitr)
- [Cloud SQL Terraform controls](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/sql_database_instance)
- [Direct Cloud Run IAP and external access](https://docs.cloud.google.com/run/docs/securing/identity-aware-proxy-cloud-run)

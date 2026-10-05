# ADR 0010: Hosted fixture demo and deployment identity

Date: 2026-10-05

Status: **Proposed for project architect review.**

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

## Access and fixture policy decisions

Choose password-protected reviewer access over HTTPS for the first hosted rehearsal (recommended), or anonymous read-only access after concurrent-load and request-limit checks. Keep database, Redis, worker commands and deployment controls off the public network. Credentials and provider keys do not enter images or deployment records. Public errors remain sanitized.

Explicitly accept or revise [ADR 0004](0004-southbank-fixture-map.md) before publishing its fixture map policy: stable Southbank identity, points on the boundary included with no buffer, locally rendered map without a basemap, position freshness at 120/300 seconds; service coverage has no TTL and current denotes the latest complete authored snapshot, not verified live freshness. This demo decision cannot silently approve live-source freshness or licensing.

## Delivery sequence after acceptance

1. Package: build static web and API images, pin dependency images, separate hosted configuration from development Compose, inject credentials and label fixture mode. Verify the actual images in an isolated stack.
2. Identity: use GitHub OIDC with scoped GCP Workload Identity Federation, separate build/deploy/runtime identities, and an Artifact Registry repository. Review the exact roles, project, region, capacity and resource plan before provisioning. [Federation guidance](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines) avoids a stored service-account key.
3. Promotion: successful main-commit CI builds once, records image digests, verifies those images and deploys that manifest. Serialize deployments. PRs validate without deployment credentials. Infrastructure bootstrap remains separate from ordinary application deployment.
4. Rehearsal: capture the previous manifest and verified backup, stop affected workers, run the reviewed migration/import sequence once, start services, then verify city/health/browser behavior before marking deployment successful. Record failures without replacing the last verified rollback target.

A deployment record contains environment, full source SHA, CI/build links for that SHA, every runtime image digest, schema revision, non-secret configuration revision and previous verified manifest. [Artifact Registry digest pulls](https://docs.cloud.google.com/artifact-registry/docs/docker/pushing-and-pulling) identify the bytes to deploy. Record registry manifest digests rather than treating a local image configuration ID as a registry digest.

Rollback reuses the recorded images only when the schema remains compatible. Otherwise stop deployment and follow a reviewed restore or forward-fix procedure; never auto-downgrade or delete retained history. Restore rehearsal includes fixture inputs and durable delivery/audit records. Backup destination, retention and recovery expectations require acceptance before provisioning.

## Acceptance cases

- Given a clean target and a verified manifest, deployment serves the three-domain fixture map over HTTPS and exposes its commit identity; API/database/worker administration stays private.
- Given identical image digests, recreating the app uses the same artifacts without rebuilding a branch and retains the selected import and durable delivery state.
- Given a failed import, migration or city smoke check, deployment remains failed and the previous verified target stays recorded; dependency readiness alone cannot publish success.
- Given a schema-compatible prior manifest, rollback restores the observed city experience; incompatible rollback fails explicitly without deleting data.
- Given a host restart and a restored backup in a separate target, city inputs, queue state and recovery behavior are verified before access is enabled.
- Given the selected access mode, unauthorized access and concurrent requests are tested against agreed limits. Synthetic/live labels and source attribution remain visible.

Record observations and resource measurements before selecting capacity. Source access (SRC-02), continuous capture (CLOUD-01), production telemetry and warehouse delivery remain separate work. This proposal contains no cloud deployment or provisioned resources.

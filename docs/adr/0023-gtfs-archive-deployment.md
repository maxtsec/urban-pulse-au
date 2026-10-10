# ADR 0023: Static archive deployment and historical seed identity

Date: 2026-10-10

Status: **Local short-lived impersonation for retained timetable seeds accepted by the project architect on 2026-10-10.** Daily keyless archival and prefix-scoped create+get were accepted on 2026-10-08 in the [archive design](../architecture/gtfs-schedule-archive.md). Resource settings, alert thresholds, temporary grants and cloud activation require their own saved-plan/operator review.

## Decision

Use a separate `infra/schedule-archive` root and state prefix. A new private archive bucket avoids exposing static data through the home collector's existing bucket-wide landing grants. The archive runtime has only object create+get under `static/gtfs-tram/`; no list, delete, overwrite, SQL, secret or metrics-write grant. Its Scheduler uses a different identity with invoker on this Job alone. Weather/DAM and the running home collector retain their existing boundaries.

Cloud checks use the expected Cloud Run metadata identity. Historical seeds run on the operator's machine with the existing named Google user login, impersonating that same archive SA. An approved administrator grants conditional, time-limited `roles/iam.serviceAccountTokenCreator` **on that SA only**, then removes the exact binding after the seed and verifies removal. No project/organization-wide grant, service-account key, policy exception or home-uploader access is needed. The seed requests a 15-minute token; the worker deadline remains at most nine minutes. Removing the grant prevents new tokens but does not revoke an already issued token before expiry.

Impersonation is an explicit seed-only option. `check` and `inspect` reject it. The command captures the token internally and suppresses authentication error bodies; operators do not print or paste tokens. A retained statewide ZIP stays local. Only its exact tram member and source/hash provenance are published, retaining unknown original download times as unknown.

A one-off seed image was considered: it avoids desktop impersonation but adds image delivery and a separate format for staging validated tram-only input. Local short-lived impersonation keeps the existing retained-source validation path and was selected.

## Deployment review

Proposed finite profile: one task, one CPU, 2 GiB, no task retries, 900-second platform timeout and a 540-second supervised runner. Memory includes the bounded statewide and tram temporary ZIPs. Startup, peak memory and real upload time must be measured before activation. Parallelism one limits a single execution; separate executions can overlap. Unique attempt paths and create-only checksum reconciliation handle duplicate dispatch.

Scheduler is initially paused and both alert policies disabled. Daily UTC scheduling avoids a 25-hour daylight-saving gap. The initial last-success candidate is a **24-hour 30-minute positive-success window**, not an absence policy: log-based/custom metrics only support the most recent 25 hours even though some system metrics support longer PromQL lookbacks. The earlier 26-hour suggestion is unsuitable for this log metric. Thresholds and notification channels are not enrolled by accepting this ADR. See the [deployment runbook](../runbooks/gtfs-archive-deployment.md) for sparse-series, never-success and recovery checks.

No apply, temporary IAM grant, upload or unattended collection is authorized by merging implementation. Retained seed and daily archive acceptance still precede the Phase 1a export.


## Regional correction proposed after initialization

The first live apply confirmed that Cloud Scheduler does not support Melbourne; its project ListLocations response includes Sydney only within Australia. Propose `australia-southeast1` for the scheduling control plane, targeting the existing `australia-southeast2` Cloud Run Job. The source download, temporary data and archive bucket remain in Melbourne. This does not add cross-region data replication or a new identity. The replacement saved plan adds only the paused Scheduler; region correction and apply await architect approval. See [provider locations](https://docs.cloud.google.com/scheduler/docs/locations).

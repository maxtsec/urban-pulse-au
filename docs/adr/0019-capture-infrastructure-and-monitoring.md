# ADR 0019: Capture landing infrastructure and monitoring

Date: 2026-10-08

Status: **Accepted by the project architect on 2026-10-08** for the same-identity telemetry permission, five operational monitoring categories and staged raw-first activation below. Resource application, private thresholds/channel selection, exporter acceptance and live activation are separate gates.

## Decision

Implement CLOUD-01 in the independent `infra/capture` Terraform root. Use a private Standard landing bucket in Melbourne (`australia-southeast2`), aligned with the existing project region. Store only selected-area normalized records/manifests and referenced static material; raw and secrets stay on the encrypted collector volume. Keep uniform bucket IAM, enforced public-access prevention, no force deletion and Terraform/provider deletion protection. Preserve the provider's seven-day soft-delete protection explicitly. Create-only upload does not need object versioning.

Keep [ADR 0018](0018-capture-delivery-and-expiry.md)'s bucket-scoped objectCreator and custom **only `storage.objects.get`** grants. They permit known-name content reads, although the confirmation adapter must use metadata only. No list/delete/overwrite or project-wide Storage data grant is added.

**Amend ADR 0015:** the same dedicated collector identity additionally receives a project-bound custom role containing **only `monitoring.timeSeries.create`**. Descriptors and policies are created by the operator through Terraform. Do not grant metricWriter, descriptor-read/create, alert/channel administration or project Storage privileges to the collector. No new long-running cloud service or third local key is introduced.

This permission cannot be confined to the selected metric names, labels or collector alias. A compromised uploader key can submit other permitted time-series data in the project, forge operational signals and consume monitoring quota. It cannot administer the alert policies through this grant. A separate telemetry identity/key would separate credentials but add rotation/storage work; the architect selected the shared identity and accepted its project-level telemetry-write scope. Revoke/rotate that key for both upload and telemetry if compromised; telemetry from that identity is not independent proof of source truth.

## Monitoring

The accepted categories are missing heartbeat, stalled successful capture per feed, stalled uploads, low bytes and low inodes. Upload monitoring includes oldest-unconfirmed age so other successful uploads cannot hide a stuck object. Use a stable logical collector alias on a `generic_task` resource; process/session/capture IDs, hostnames and IPs are not metric labels. Three fixed feed labels bound cardinality.

Expose integer gauges under `custom.googleapis.com/urbanpulse/collector/v1/`:

| Metric | Meaning |
| --- | --- |
| `heartbeat` | 1 when the live collection loop produces a current pulse; not a source-health claim |
| `capture_success_known{feed}` | 1 when a durable successful live-capture timestamp exists; otherwise 0 |
| `capture_age_seconds{feed}` | Age of that timestamp, omitted if unknown |
| `upload_success_known` | 1 when a durable generation/checksum-validated confirmation exists; otherwise 0 |
| `upload_age_seconds` | Age of the last such confirmation, omitted if unknown |
| `upload_pending_age_seconds` | Age of the oldest required unconfirmed upload; 0 only when the durable queue is known empty; omitted if queue state is unknown |
| `free_bytes` / `free_inodes` | Available capacity of the mounted encrypted data filesystem for the collector UID |

Use the resource labels exported by Terraform and UTC observation times; timestamp/clock regression must not manufacture a fresh success. Do not emit fixture/dry-run data into the enrolled live alias. No extrapolated success, zero-filled unknown age or fake upload confirmation is allowed. The exporter must validate timestamps and use a bounded request/retry budget; the [runtime runbook](../runbooks/collector-continuous.md#authenticated-raw-only-exporter) defines its explicit configuration and failure behavior.

Heartbeat absence has a configurable private interval. Each feed and upload policy tests both age and explicitly unknown success; upload also tests pending age. Capacity thresholds must warn above the configured local hard stop. Missing threshold data does not trigger a violation (`EVALUATION_MISSING_DATA_INACTIVE`); heartbeat absence owns notification for host/exporter silence. Explicit measured unknown success (`*_success_known=0`), old captures/uploads and low capacity still trigger their policies. All alerts initially remain disabled. Four independently enabled/enrolled groups are `heartbeat`, `capture` (all three feeds), `capacity` (bytes and inodes) and `upload`. Each enabled group requires its own enrollment evidence and nonempty verified notification-channel references, followed by a fresh-point/loss/recovery drill. Terraform's enrollment flag records operator evidence; it cannot verify notification receipt.

Google documents that [metric absence requires prior measurements](https://docs.cloud.google.com/monitoring/alerts/metric-absence). A series that has never emitted cannot be assumed monitored. Inventory and exercise the streams of each group being enrolled with truthful values, then verify point arrival again after its alert-policy change. Raw-only enrollment requires heartbeat, per-feed capture and capacity evidence; upload streams and confirmations are not prerequisites. Before enabling upload, separately exercise its confirmed, unknown and pending-queue states. Missing health data can close existing threshold incidents; neither that closure nor automatic closure of an absence incident proves recovery. Check fresh measurements and measured progress. Partial loss of a health stream while heartbeat continues is a telemetry gap, not covered by a second absence alert; exporter acceptance must exercise partial-write reporting and stream completeness. Planned manual-unlock maintenance remains a gap; an operator may use a time-bounded Monitoring snooze and must verify resumed points/notifications after it expires.

## Retention and rollout

The existing normalized-history policy is 12 months; raw 14 days remains a proposal. This infrastructure bootstrap adds **no automatic object deletion or locked retention policy**. A later reviewed expiry implementation must distinguish normalized records from manifests/static references still needed for replay, respect the accepted horizon and test deletion evidence before enabling a lifecycle rule. Soft delete is a recovery period after deletion, not the normalized retention policy.

Keys are never generated by Terraform or stored in state. The operator creates the accepted key only after IAM readback/denial checks and encrypted-host acceptance. Use reviewed saved plans; keep variables, channels, state and plan artifacts private. The existing operator-controlled GCS state backend may use a distinct `capture/` prefix; the uploader gets no state-bucket access. This root does not reuse the CD deployer or modify serving infrastructure.

Mock plans prove configuration behavior only. The architect selected raw-first rollout (A): before unattended raw capture, verify encrypted-host and source acceptance, telemetry IAM, authenticated exporter delivery, heartbeat/capture/capacity conditions and notifications, locked/offline absence and recovery. Keep upload disabled and unenrolled until normalization/uploader implementation, Storage IAM denial tests, non-composite generation-pinned metadata confirmation and upload-specific notification drills pass. Raw-only operation must retain all bytes, warn above reserves and stop safely at the hard reserve; it is capacity-bounded, not permission to collect indefinitely without expiry. [The infrastructure runbook](../runbooks/capture-infrastructure.md) records the sequence. No resource, key or live source is enabled merely by merging this decision.

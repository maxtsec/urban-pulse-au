# ADR 0015: Operator-hosted capture collector and scoped upload key

Date: 2026-10-07

Status: **Accepted by the project architect on 2026-10-07** for the hosting, retention tiers and upload identity below. Polling cadence was additionally accepted on 2026-10-07: positions 60 seconds, trip updates 120 seconds and alerts 60 seconds. Normalized retention of 12 months, collected-grain Southbank plus Melbourne CBD history, DTP/CC BY 4.0 attribution and dedicated-host use were subsequently accepted. Raw duration remains proposed at 14 days after the latest review. [ADR 0018](0018-capture-delivery-and-expiry.md) accepts v3 persistence, B metadata confirmation (replacing the separate confirmation-bucket option) and the manual-unlock host policy. This decision provisions no resources and enables no live source.

Resolves the capture-host part of A-06. Amends [ADR 0010](0010-hosted-fixture-demo.md)'s keyless-identity direction for one named upload identity only. Source-use approval, SRC-02 live-access proof and the [capture contract](../architecture/capture-event-contract.md) remain separate gates.

## Context

Provider feeds cannot be requested per area: GTFS-Realtime returns the whole tram network and the warning feed covers the state. Raw captures are therefore the largest data layer, while UrbanPulse needs selected-area history. The [hosting comparison](../architecture/early-capture-options.md) listed local, free-tier, regional VM, worker-pool and shared-host options. Continuous cloud compute and raw object storage add recurring cost before any source has been measured.

## Decision

**Hosting.** Run the collector on a dedicated, operator-managed, always-on Linux host outside Google Cloud. The development workstation is not the collector. Host details are kept in private operator notes, not the repository.

**Tiered retention.** Fetch complete provider feeds. Keep exact raw bytes and capture manifests on the collector host for a short window, used for debugging, reprocessing and short backfill. Normalize on the host, filter to the selected areas, and upload only the resulting records and manifests to Google Cloud for long-term use. Capture-time area filtering of raw payloads is rejected: it would break exact-byte replay, trip updates lack coordinates, and later areas could not be backfilled.

**Tram cadence (accepted 2026-10-07).** Collect positions / trip updates / alerts every **60 / 120 / 60 seconds**, preferring retained history over minimum live latency. The [collection policy](../architecture/tram-collection-policy.md) records storage estimates, shared request/retry limits and remaining activation gates. This does not change fixture freshness or the animation display-delay version.

**Upload identity.** Use one dedicated service account with `roles/storage.objectCreator` plus a custom role containing only `storage.objects.get`, both bound to the dedicated landing bucket. The 2026-10-07 B amendment in ADR 0018 replaces the original write-only grant and supersedes separate-bucket confirmations. Get allows content and metadata for known names; the implementation uses metadata only. The identity cannot list, overwrite or delete objects and has no project-wide data role. Its JSON key is the single accepted exception to keyless identities. Runtime, Job, deployer and builder identities remain keyless.

## Key handling

- Store the key only on the collector host, readable only by the collector service account, outside the repository and any synchronized folder. Never put it in images, logs, GitHub or Terraform state.
- Create keys through a reviewed operator step. If the organization enforces `iam.disableServiceAccountKeyCreation`, a project-scoped exception needs separate approval; never relax it organization-wide.
- Rotate on a fixed schedule: create a replacement, deploy it, verify an upload, then delete the old key. Revoke immediately on suspected exposure or host compromise. Record key IDs and rotation dates privately.
- Uploads use unique, create-only object names derived from capture identity, with `ifGenerationMatch=0`; the identity has no delete permission to replace earlier records.

## Upload confirmation

The collector owns a local pending-upload record per object until GCS metadata confirms its exact generation, size and service-calculated checksums under [ADR 0018 B](0018-capture-delivery-and-expiry.md#accepted-cloud-confirmation-b).

- Persist local SHA-256, CRC32C, MD5 and size before a single-request, non-composite create-only upload with service-validated checksums.
- Confirm a successful response only after matching its generation, identity, size and both service checksums. After a lost response or HTTP 412, read known-object metadata (no content download), pin the returned generation and apply the same checks. Custom SHA metadata is not independent evidence.
- Missing fields remain unconfirmed; mismatches or composite objects are quarantined and never overwritten. No separate confirmation bucket or cloud verifier is part of accepted B.
- Pending records, and the raw bytes they derive from, are kept beyond the normal raw window until confirmed. Disk alerts account for this backlog.

## Host requirements

- An operating system with current security updates and automatic security patching. The accepted [ADR 0018 amendment](0018-capture-delivery-and-expiry.md#host-encryption-and-rollout) uses a dedicated encrypted data/key volume with manual unlock, encrypted or disabled swap, controlled maintenance reboots and no automatic reboot. No public inbound service ports; private operator SSH remains permitted.
- Wired network where possible, NTP time synchronization, auto-start under a service manager, and no sleep.
- Disk capacity for the raw window plus headroom, with an alert before it fills. Removable storage must fail loudly when detached rather than writing elsewhere.
- One active collector. A local lock prevents duplicate writers; any move to another host transfers the lease and records the gap.
- The provider API key is a separate local secret with the same storage rules as the upload key.

## Monitoring

The collector sends a periodic heartbeat. A cloud-side check alerts when no heartbeat or upload arrives within an agreed threshold. Capture gaps, including planned maintenance, are recorded in the manifests and evidence. Alert destinations and thresholds stay private.

## Consequences

- Cloud compute and raw object storage are avoided for the largest layer; normalization load moves to the collector host.
- Availability follows the host's power, network and maintenance. Gaps are expected, recorded and not hidden by later data.
- Raw bytes are lost if the host disk fails. Uploaded records survive. Older raw replay beyond the window is explicitly not guaranteed.
- A long-lived key exists. Its blast radius covers creating and reading known objects in one bucket, without list/delete, at the cost of rotation discipline and host hardening.
- The collector and normalizer run as a container so the same code can later move to cloud hosting. The capture contract's create-only and manifest rules apply to local storage as they would to object storage.

## Open items

- Raw retention duration: separately proposed at 14 days. Normalized duration, scope/grain and attribution are accepted above; expiry implementation and live activation remain separate.
- Landing bucket, scoped create/get upload identity, heartbeat alert and collector metadata reconciliation: provisioned in CLOUD-01 through reviewed infrastructure code. CLOUD-01 acceptance includes a lost-acknowledgement retry that is reconciled rather than assumed successful.
- How uploaded records load into the serving database or warehouse: decided with A-07/HIST-01.
- Tram catalogue attribution/use is accepted under the collection policy; confirm subscription scope before unattended capture. Other sources still need their own terms and retention decisions.

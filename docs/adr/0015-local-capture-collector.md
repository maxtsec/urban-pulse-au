# ADR 0015: Operator-hosted capture collector and scoped upload key

Date: 2026-10-07

Status: **Accepted by the project architect on 2026-10-07** for the hosting, retention tiers and upload identity below. Retention durations, long-term grain and polling cadence remain open until SRC-02 measurements. This decision provisions no resources and enables no live source.

Resolves the capture-host part of A-06. Amends [ADR 0010](0010-hosted-fixture-demo.md)'s keyless-identity direction for one named upload identity only. Source-use approval, SRC-02 live-access proof and the [capture contract](../architecture/capture-event-contract.md) remain separate gates.

## Context

Provider feeds cannot be requested per area: GTFS-Realtime returns the whole tram network and the warning feed covers the state. Raw captures are therefore the largest data layer, while UrbanPulse needs selected-area history. The [hosting comparison](../architecture/early-capture-options.md) listed local, free-tier, regional VM, worker-pool and shared-host options. Continuous cloud compute and raw object storage add recurring cost before any source has been measured.

## Decision

**Hosting.** Run the collector on a dedicated, operator-managed, always-on Linux host outside Google Cloud. The development workstation is not the collector. Host details are kept in private operator notes, not the repository.

**Tiered retention.** Fetch complete provider feeds. Keep exact raw bytes and capture manifests on the collector host for a short window, used for debugging, reprocessing and short backfill. Normalize on the host, filter to the selected areas, and upload only the resulting records and manifests to Google Cloud for long-term use. Capture-time area filtering of raw payloads is rejected: it would break exact-byte replay, trip updates lack coordinates, and later areas could not be backfilled.

**Upload identity.** Use one dedicated service account whose only grant is `roles/storage.objectCreator` on one dedicated landing bucket. It cannot read, list, overwrite or delete objects and has no other project role. Its JSON key is the single accepted exception to keyless identities. Runtime, Job, deployer and builder identities remain keyless.

## Key handling

- Store the key only on the collector host, readable only by the collector service account, outside the repository and any synchronized folder. Never put it in images, logs, GitHub or Terraform state.
- Create keys through a reviewed operator step. If the organization enforces `iam.disableServiceAccountKeyCreation`, a project-scoped exception needs separate approval; never relax it organization-wide.
- Rotate on a fixed schedule: create a replacement, deploy it, verify an upload, then delete the old key. Revoke immediately on suspected exposure or host compromise. Record key IDs and rotation dates privately.
- Uploads use unique, create-only object names derived from capture identity, so a write-only identity cannot replace earlier records.

## Host requirements

- An operating system with current security updates, automatic security patching, full-disk encryption and no inbound service ports.
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
- A long-lived key exists. Its blast radius is limited to creating objects in one bucket, at the cost of rotation discipline and host hardening.
- The collector and normalizer run as a container so the same code can later move to cloud hosting. The capture contract's create-only and manifest rules apply to local storage as they would to object storage.

## Open items

- Raw retention per feed, long-term areas and grain, and polling cadence: decide from SRC-02 measurements of payload size, compression, update interval and unchanged-snapshot ratio.
- Landing bucket, upload identity and heartbeat alert: provisioned in CLOUD-01 through reviewed infrastructure code.
- How uploaded records load into the serving database or warehouse: decided with A-07/HIST-01.
- Source terms: confirm each source permits the planned local and cloud retention before enabling it.

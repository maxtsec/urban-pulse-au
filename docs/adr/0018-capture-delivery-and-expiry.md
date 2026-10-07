# ADR 0018: Capture delivery, confirmation and expiry

Date: 2026-10-07

Status: **Persistence mechanism accepted by the project architect on 2026-10-07, with the conditions below.** Cloud confirmation and host unlock alternatives have separate decision states below. Raw retention is separately proposed at 14 days, following the latest review. This decision enables no resources or live sources.

## Scope and source policy

Fetch complete tram feeds at the accepted 60/120/60-second cadence. Preserve normalized Southbank and Melbourne CBD history at the collected grain for 12 months, without sampling or a health score. Keep source/capture times, completeness, failures and coverage. DTP/CC BY 4.0 attribution is accepted under the [collection policy](../architecture/tram-collection-policy.md). Supporting static schedule/boundary material remains available while referenced.

**14 days remains proposed**, not an expiry default. Raw duration needs a separate accepted, versioned policy before deletion. Accepting this mechanism does not select the duration.

Positions use the accepted polygon coverage rule; trip updates use pinned static trip/stop linkage; alerts use selectors. Unresolved linkage is not absence of disruption: preserve raw and report unresolved counts rather than guessing membership or silently discarding it. Normalization records area/static tram-member hashes, receipt time and provider observation time separately.

## Accepted persistence and recovery

Use a **fresh capture-store-v3**; retain the rehearsed v2 store and image unchanged. V3 preserves immutable capture evidence, cumulative accounting and direct sequence lookup. Older code refuses v3 rather than misinterpreting expired payloads.

Use existing publication/fsync primitives. Keep normalization progress separate from per-object upload progress. Scope a bounded normalizer cursor by store UUID and normalizer/area/static versions. Publish deterministic output and a create-only completion manifest before advancing it. Every required upload has a durable pending record with name, SHA-256, service-validated checksum, byte count and source capture pins before network I/O. Retries verify/reuse the same records and identity.

Capture and downstream passes have independent bounds. Network uploads run outside store ownership against immutable files; state publication and expiry checks hold ownership. Verification holds block capture and expiry. Reserve/backlog checks stop collection without deleting pinned data when capacity is exhausted.

### Expiry protocol

All four conditions must hold together:

1. The capture has passed its separately accepted retention period.
2. Normalization is complete, with no unresolved/quarantined source evidence.
3. Every required upload is confirmed against its expected identity and bytes.
4. No verification hold or integrity block exists.

Publish and fsync a create-only expiry intent containing original receipt hash, size, policy, eligibility time and normalization/confirmation references. Unlink **only `response/payload.bin`**, fsync its directory, then publish completion. Keep intent, receipt, manifest and sequence index. Recovery may finish the recorded unlink; it cannot manufacture an expiry record to excuse missing bytes.

V3 verify accepts missing payload only with a valid prior expiry record and checked eligibility/provenance. Missing bytes without it are corruption. Retained bytes still receive full hash verification. Cumulative capture/outcome counts and contiguous lookup remain intact; report retained/expired payload totals separately. Intent published before a crash may coexist with payload: recovery safely finishes or retries without double counting.

Crash tests terminate the process at each record-write/publication, unlink and directory-fsync boundary, including completion publication. Also test corrupt/missing expiry evidence, holds, unconfirmed uploads, incomplete normalization, repeated recovery and clock rollback. No bulk directory deletion or unrecorded cleanup is permitted.

### Metadata capacity limitation

Metadata has no automatic deletion in this slice. The review estimate is about **84 MiB/day**, or about **30 GiB/year**, of metadata/filesystem allocation at this cadence, not a measured guarantee. Payload expiry does not reclaim these files/inodes. Measure actual growth and include it in reserve planning. A separate metadata-compaction design must preserve sequence, provenance and crash recovery before capacity becomes a limit.

## Cloud confirmation alternatives

Previously accepted A retains landing objectCreator and permits reading a separate confirmation bucket. The latest review prefers B; **replacement of A by B awaits explicit selection**. Neither is provisioned yet.

| | A: Separate confirmations | B: Known-object readback |
| --- | --- | --- |
| Host permission | Landing objectCreator; confirmation-bucket read | Landing objectCreator plus a bucket-bound custom role containing only `storage.objects.get` |
| Reconciliation | Bounded scheduled cloud verifier checks bytes and writes confirmations | Collector reads the known object after an unknown outcome/412 |
| Read exposure | Confirmation names/hashes | Normalized data and metadata for known names; not metadata-only access |
| Components | Verifier, confirmation storage and verifier monitoring | No cloud reconciliation component |
| Failure | Verifier outage pins raw; alert on confirmation age and disk reserve | Readback outage pins raw; alert on pending age and disk reserve |

B must not use objectViewer, which includes list. It grants no list/delete/overwrite or project-wide data access. [Google's permission reference](https://docs.cloud.google.com/storage/docs/access-control/iam-permissions) confirms get reads both content and metadata. Landing contains normalized public-source data, not raw responses or secrets; this nevertheless increases the key's read capability.

Both options use create-only uploads (`ifGenerationMatch=0`) and service-validated checksums. A 412 alone never confirms an upload. Pin readback to the returned object generation and compare actual bytes/hash and size against the durable expected record; uploader-authored SHA metadata alone is not independent proof. Mismatch quarantines and pins raw; never overwrite a conflicting object. Successful upload and later reconciliation publish the same durable confirmation outcome.

Use a separate Terraform root and review saved plans before apply. Keys stay outside Terraform/images/source and follow [ADR 0015](0015-local-capture-collector.md). Heartbeat, failed-feed, pending-age and disk/inode monitoring is required for either option; B removes reconciliation infrastructure, not monitoring.

## Host encryption and rollout

**Accepted by the architect on 2026-10-07: preserve the existing installation, use a dedicated encrypted collector data volume with manual unlock, and disable automatic reboot while retaining automatic security updates.** The operator schedules maintenance/reboots, unlocks the volume afterwards and accepts recorded collection gaps. This replaces ADR 0015's full-disk-encryption requirement for this host, not its dedicated-operation requirement.

Raw, exports and both keys reside on the encrypted volume. Disable or encrypt swap and exclude secrets from dumps/logs. Bind services to the mounted encrypted filesystem so a failed unlock cannot write into the underlying unencrypted directory. No key file on the unencrypted root may substitute for manual unlock. Never place the passphrase in agent sessions, commands, logs or source.

Before a concrete host change, review the exact volume path, capacity, creation procedure and swap/service configuration. Preserve the existing system and v2 rehearsal. Use an interactive operator terminal for the passphrase/recovery material. Test locked-volume refusal and post-unlock recovery before installing provider/upload keys. Cloud heartbeat-loss monitoring must work while the host/volume is offline; maintenance gaps remain visible, not silently exempted. Private operator notes hold paths, host details, maintenance schedule and alert destinations.

TPM2 unattended unlock was considered but is not a prerequisite of the selected manual policy. Reinstalling with full-disk encryption would not itself provide unattended unlock. Both alternatives would require a new explicit unlock/recovery decision.
Implement scheduler, normalization, upload/expiry recovery, infrastructure/monitoring and host service in reviewable changes. Test locally before plans; apply only reviewed plans, then perform separately authorized finite live acceptance with duration/request bounds before unattended operation. Measure allocated bytes/inodes and gaps. Weather/hazard/planning sources retain separate SRC-02 gates; completing tram capture does not claim those sources are enabled.

# ADR 0018: Capture delivery, confirmation and expiry

Date: 2026-10-07

Status: **Persistence mechanism accepted by the project architect on 2026-10-07, with the conditions below.** The architect additionally accepted B (known-object metadata confirmation), replacing A, and the manual-unlock host policy on 2026-10-07. Raw retention is separately proposed at 14 days, following the latest review. This decision enables no resources or live sources.

[ADR 0019](0019-capture-infrastructure-and-monitoring.md) records the 2026-10-08 accepted addition: the same collector identity may write Monitoring time series through a project-scoped custom role containing only `monitoring.timeSeries.create`. Storage permissions remain confined to the landing bucket.

## Scope and source policy

Fetch complete tram feeds at the accepted 60/120/60-second cadence. Preserve normalized Southbank and Melbourne CBD history at the collected grain for 12 months, without sampling or a health score. Keep source/capture times, completeness, failures and coverage. DTP/CC BY 4.0 attribution is accepted under the [collection policy](../architecture/tram-collection-policy.md). Supporting static schedule/boundary material remains available while referenced.

**14 days remains proposed**, not an expiry default. Raw duration needs a separate accepted, versioned policy before deletion. Accepting this mechanism does not select the duration.

Positions use the accepted polygon coverage rule; trip updates use pinned static trip/stop linkage; alerts use selectors. Unresolved linkage is not absence of disruption: preserve raw and report unresolved counts rather than guessing membership or silently discarding it. Normalization records area/static tram-member hashes, receipt time and provider observation time separately.

## Accepted persistence and recovery

Use a **fresh capture-store-v3**; retain the rehearsed v2 store and image unchanged. V3 preserves immutable capture evidence, cumulative accounting and direct sequence lookup. Older code refuses v3 rather than misinterpreting expired payloads.

Use existing publication/fsync primitives. Keep normalization progress separate from per-object upload progress. Scope a bounded normalizer cursor by store UUID and normalizer/area/static versions. Publish deterministic output and a create-only completion manifest before advancing it. Every required upload has a durable pending record with name, SHA-256, service-validated checksum, byte count and source capture pins before network I/O. Retries verify/reuse the same records and identity.

### Phase 1a isolation and Phase 1c upload-pin amendment

Accepted by the project architect on 2026-10-08: Phase 1a reads finalized raw without acquiring or writing the live store. With expiry disabled, export inventory, pending and confirmations live in a separate encrypted export directory with its own lock. They provide retry/provenance, not raw pins or expiry authorization; the running collector needs no stop or upgrade.

Phase 1c introduces contiguous store-scoped capture-sequence ranges plus immutable inventory hashes for automated upload pins, replacing the implemented maximum of 32 inline capture references per object. The [normalized contract](../architecture/normalized-tram-contract.md#sequence-range-upload-pins) specifies versioned records, inventory publication, completeness/confirmation checks and compatible collector/verifier rollout. Legacy records retain their original meaning. Revalidate export-local evidence before any integration into expiry state; the amendment does not relax the four expiry conditions.

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

## Accepted cloud confirmation: B

**Accepted by the project architect on 2026-10-07: B replaces the previously accepted A.** Keep `roles/storage.objectCreator` on the dedicated landing bucket and add a custom role containing **only `storage.objects.get`**, bound to that bucket. No objectViewer, list, delete, overwrite or project-wide Storage data access. This amends ADR 0015's write-only boundary. No separate confirmation bucket or cloud reconciliation service is required.

| | A: Separate confirmations (superseded) | B: Known-object metadata (accepted) |
| --- | --- | --- |
| Host read exposure | Confirmation names/hashes | Normalized data and metadata for known names |
| Reconciliation | Scheduled cloud verifier writes confirmations | Collector reads GCS metadata for a known object |
| Components | Verifier, confirmation storage and verifier monitoring | No cloud reconciliation component |
| Failure | Verifier outage pins raw | Metadata readback outage pins raw |

B removes a reconciliation dependency and its operation cost. Landing holds normalized public-source records, not raw responses or secrets. IAM cannot restrict get to metadata: the key can also read object content if the name is known, even though this workflow never downloads it. The [permission reference](https://docs.cloud.google.com/storage/docs/access-control/iam-permissions) distinguishes get from list. Both provider and upload keys retain their separate revocation procedures.

### Upload and metadata confirmation

1. Before upload, persist expected bucket/name, exact byte count, SHA-256, CRC32C and MD5 of the immutable output bytes. Encode CRC32C as base64 big-endian and MD5 as base64, matching the [GCS object fields](https://docs.cloud.google.com/storage/docs/json_api/v1/objects). SHA-256 remains local provenance; custom `metadata.sha256` is not confirmation evidence.
2. Use a **single-request, non-composite** upload with `ifGenerationMatch=0` and GCS-validated checksums. A JSON API multipart request containing metadata and one payload is still one request; it is not XML multipart upload or parallel compose. Do not use compose or transparently switch upload protocols. [GCS validates supplied checksums against received bytes](https://docs.cloud.google.com/storage/docs/data-validation).
3. A lost response or HTTP 412 keeps the object pending. Fetch [object metadata](https://docs.cloud.google.com/storage/docs/json_api/v1/objects/get) for its known bucket/name, without `alt=media`; do not download contents. Read bucket, name, generation, size, `crc32c`, `md5Hash` and `componentCount`. Bind the confirmation to that returned generation; any follow-up read for it specifies that generation. Never combine fields from different generations or silently adopt a replacement.
4. Confirm only when identity, size and **both server-calculated CRC32C and MD5** match the durable expected record, and the object is non-composite. Composite objects lack MD5. Missing/malformed checksum or generation fields never downgrade validation to size-only or custom metadata. Unsupported metadata stays unconfirmed; a definite identity/size/checksum mismatch or composite object is quarantined. Neither outcome releases raw pins or overwrites the remote object. A transient failure/404 remains pending for bounded retry.
5. Persist the same confirmation record for acknowledged upload and reconciliation, including generation, size and service checksums. A successful upload response must pass the same field comparisons, using metadata lookup if its response is insufficient. Only durable confirmation releases the corresponding upload pin; raw expiry still requires all four eligibility conditions above.

CRC32C/MD5 establish the accepted transfer-integrity check; they are not a SHA-256 content readback or proof against deliberate checksum collisions. A future change requiring such proof needs a separate decision rather than an unannounced content download.

Acceptance covers lost acknowledgement then matching 412, wrong size/checksum, missing checksum, unexpected composite object, generation changes, retry after process termination, and a crash before local confirmation publication. Verify that the adapter issues metadata requests only, that the custom role contains exactly get, and that the bucket grants neither list nor delete. Do not infer IAM enforcement from unit mocks: exercise allowed metadata access and denied operations against the deployed identity before unattended activation.

Use a separate Terraform root and review saved plans before apply. Keys remain outside Terraform/images/source and follow [ADR 0015](0015-local-capture-collector.md). Heartbeat, failed-feed, pending-age and disk/inode monitoring remain mandatory. B removes the verifier dependency, not network/readback failures: raw stays pinned on those failures and the collector stops at its reserve rather than deleting unconfirmed evidence.

## Host encryption and rollout

**Accepted by the architect on 2026-10-07: preserve the existing installation, use a dedicated encrypted collector data volume with manual unlock, and disable automatic reboot while retaining automatic security updates.** The operator schedules maintenance/reboots, unlocks the volume afterwards and accepts recorded collection gaps. This replaces ADR 0015's full-disk-encryption requirement for this host, not its dedicated-operation requirement.

Raw, exports and both keys reside on the encrypted volume. Disable or encrypt swap and exclude secrets from dumps/logs. Bind services to the mounted encrypted filesystem so a failed unlock cannot write into the underlying unencrypted directory. No key file on the unencrypted root may substitute for manual unlock. Never place the passphrase in agent sessions, commands, logs or source.

Before a concrete host change, review the exact volume path, capacity, creation procedure and swap/service configuration. Preserve the existing system and v2 rehearsal. Use an interactive operator terminal for the passphrase/recovery material. Test locked-volume refusal and post-unlock recovery before installing provider/upload keys. Cloud heartbeat-loss monitoring must work while the host/volume is offline; maintenance gaps remain visible, not silently exempted. Private operator notes hold paths, host details, maintenance schedule and alert destinations.

TPM2 unattended unlock was considered but is not a prerequisite of the selected manual policy. Reinstalling with full-disk encryption would not itself provide unattended unlock. Both alternatives would require a new explicit unlock/recovery decision.

Implement scheduler, normalization, upload/expiry recovery, infrastructure/monitoring and host service in reviewable changes. Test locally before plans; apply only reviewed plans, then perform separately authorized finite live acceptance with duration/request bounds before unattended operation. Measure allocated bytes/inodes and gaps. Weather/hazard/planning sources retain separate SRC-02 gates; completing tram capture does not claim those sources are enabled.

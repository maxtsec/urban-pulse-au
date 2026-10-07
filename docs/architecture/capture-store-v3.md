# Capture store v3

The v3 format implements the first persistence slice of [ADR 0018](../adr/0018-capture-delivery-and-expiry.md). It introduces downstream records and reads expiry evidence. It has **no expiry writer, raw-delete command, live uploader or normalizer**. Raw duration remains a separate decision; no 14-day default is installed.

## Version and ownership

Create a fresh store using `--store-version v3`; keep the v2 rehearsal and its pinned image unchanged. The default CLI still selects v2 for fixture compatibility; `run --live` rejects v2 before accessing the store, key or network. Live requires an explicit `--store-version v3`. Each journal/verifier checks its exact marker; no in-place migration or automatic version detection occurs. V3 uses the existing exclusive Linux lock, filesystem allowlist, sequence index and checksummed capture control. Ordinary recovery checks capture control/pending only, without scanning downstream history.

Each downstream mutation holds store ownership and rejects verification holds. Network work belongs outside that lock in a later adapter. Input capture evidence and downstream records are create-only; only the checksummed normalization cursor advances by atomic replacement. Temporary files from interrupted publication remain unpublished and can be inspected separately; this slice does not clean them or compact metadata.

## Layout

```text
store.json                         capture-store-v3 + store UUID
control.json                       existing capture-control-v1
captures/<uuid>/                   original intent, receipt, manifest, payload
by-sequence/<19-digit sequence>    original direct lookup
normalization/<scope hash>/
  cursor.json                      checked store/scope + contiguous progress
  records/<19-digit sequence>.json
uploads/<object identity hash>.json
confirmations/<object identity hash>.json
policies/<policy hash>.json         read-only policy evidence in this slice
expiry/<capture uuid>.intent.json  read-only expiry evidence in this slice
expiry/<capture uuid>.complete.json
```

Sessions, staging and verification holds retain their existing meaning. A missing cursor in a registered scope is corruption, not permission to start again at zero. Scope creation publishes its initial cursor and empty records directory together. Partial store initialization before the marker is published is refused on restart; preserve it for inspection and initialize another empty store.

## Downstream records

| Record | Identity and invariants |
| --- | --- |
| Capture reference | Store UUID, capture UUID, sequence and canonical full-receipt SHA-256; null receipt hash only for unsuccessful captures |
| Normalization scope | Hash of normalizer revision, selected-area revision and static tram-member revision |
| Normalization record | One immutable result per scope/sequence: complete or quarantined, unresolved count, required upload IDs, completion time |
| Upload pending | Hash of bucket/name locates the record; immutable local SHA-256, CRC32C, MD5, size and source-capture references describe expected output |
| Confirmation | Hash of pending record, object identity, exact generation, GCS CRC32C/MD5, size and confirmation time |
| Cursor | Store/scope identity, contiguous through-sequence, hash of last normalization record, document checksum |
| Retention policy | Explicit version, required normalization scope, raw duration, acceptance time and decision reference; no defaults |
| Expiry intent/completion | Exact capture/receipt, policy, normalization and confirmation hashes; eligibility and record/completion times; original payload size/hash |

CRC32C and MD5 use canonical base64 with four and sixteen decoded bytes respectively. Records are bounded to 16 KiB, with at most 32 captures per upload and 32 objects per normalization. An object has at most 8 MiB; a future normalizer must shard explicitly or reject oversized output without truncation. Object names are UTF-8 bounded; hashes identify filesystem paths rather than using provider names as local paths.

Register a scope before publishing results. Publish each pending object before a normalization record that references it, then advance the cursor by exactly one. Every capture, including an unsuccessful fetch or one with no applicable records, needs an export manifest recording outcome/coverage before successful normalization can complete. A quarantined result can advance progress, but cannot authorize expiry. Reprocessing uses a new scope/revision; it does not rewrite the earlier result. Cursor reads validate the last record and its bounded references; full historical continuity is checked by offline verify.

Confirmation publication checks local record consistency, including both expected checksums and size. **It does not contact GCS or attest that a caller performed metadata readback.** The later upload adapter must establish that evidence under accepted B before calling it. No public CLI can manufacture confirmation or retention/expiry records in this slice. Synthetic tests construct such records explicitly and do not count as cloud validation.

## Writer clock floors

Future normalizer and uploader writers must construct immutable completion times as `max(now_utc, reference_time)`. For normalization, the reference is the capture manifest completion time; for upload confirmation, it is the latest completion time among all referenced captures. Expiry intent/completion must likewise respect their validated eligibility and prior-record times. Clock rollback must not create an unpublishable immutable result. Test each writer with a clock earlier than its reference before enabling it. Preserve provider observation/receipt timestamps; these floors apply only to locally generated processing times. Use monotonic time for elapsed-time budgets.

## Expiry-aware verification

A retained payload is hashed against its receipt. A missing payload requires an expiry intent whose capture, receipt, policy, accepted scope, normalization and every confirmation agree. The verifier checks expiry timing and rejects complete normalization with unresolved records. Other unconfirmed upload records referencing that capture also prevent acceptance. A completion record must reference that intent and cannot coexist with the payload.

A valid intent without completion represents interrupted expiry whether raw is still present or absent. Verify reports `incomplete`, `expiry_pending` and `recovery_required`, retaining its pre-scan hold. It does not delete, restore or certify completion. Recovery of that operation belongs to the later expiry-writer PR. An unexplained missing payload, malformed reference or mismatching checksum is corruption and leaves the verification block/hold in place.

Reports preserve cumulative original `payload_bytes` and capture outcome counts. They separately report `retained_payload_bytes`, `expired_payload_bytes`, expired captures and downstream record counts; expired provenance is checked, not rehashed as if the bytes remained available. Past exclusive-lock/hold checks must be enforced by the future expiry writer; an offline reader cannot prove historical lock ownership from timestamps.

## Validation and subsequent work

[Validation evidence](../evidence/cloud-01-v3-store.md) records the isolated suite and persistent-volume runtime check. Linux tests terminate subprocesses during capture publication, scope publication, each pending/normalization/confirmation publication boundary, cursor replacement and verification. They assert replay-safe progress, unchanged raw bytes, no idle history scan and retained holds after interruption. Synthetic expiry fixtures cover absent/present payloads, partial completion, orphan upload pins and damaged evidence. They test the reader, not a deployed expiry writer or physical disk power-loss durability.

Subsequent PRs provide host mount protection, continuous capture/heartbeat, cloud infrastructure, real normalization/upload, then expiry execution and its unlink/fsync crash tests. No host setup, Terraform apply, retention activation or live capture is implied by format availability.

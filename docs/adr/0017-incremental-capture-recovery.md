# ADR 0017: Incremental local capture recovery

Date: 2026-10-07

Status: **Proposed; architect approval required before implementation.** Refines the file-based option A accepted in [ADR 0016](0016-local-capture-recovery.md). It does not reopen the SQLite decision, approve live capture or remove any source/retention gate. Approval must explicitly select the checkpoint design, verification semantics and store-version transition below; merging a proposal alone is not acceptance.

## Problem and current behavior

`CaptureJournal.recover()` enumerates every capture and hashes every published payload. Both `run` and `status` call it before returning or collecting. Runtime retains all evidence, so this startup cost grows with history. The current application is synchronous: `collect()` finishes one capture before admitting the next. Its status needs only outcome totals, the latest successful receipt per mode/feed and a retained Retry-After deadline.

The next implementation must reopen a growing store without reading completed historical payloads. Full historical integrity checking remains available as an explicit operation. Current implementation and outstanding live gates are tracked in the [delivery plan](../delivery-plan.md).

## Options within the accepted file journal

| Option | Benefit | Cost |
| --- | --- | --- |
| 1. One atomic control checkpoint with one pending slot (recommended) | A bounded read set on startup; pending identity and summary change together; fits the existing sequential collector | A new mutable, authoritative control record; one in-flight capture; archive corruption is detected by verify rather than every startup |
| 2. Per-capture pending entries plus a separate summary checkpoint | Natural queue if several captures later run concurrently | Multiple file publications require ordered completion/accounting and deduplication; more recovery states for no current concurrency benefit |

Both retain immutable intent/receipt/payload/manifest evidence and Linux whole-run ownership. Option 2 is viable if concurrent fetches become a reviewed requirement. A cache that can silently disappear is insufficient: missing state must not mean there is no unfinished request or Retry-After deadline.

## Proposed option 1

### Store and control record

Use `capture-store-v2` in `store.json`, including a new store UUID. Keep capture evidence records at `capture-v1` with their existing meanings and `captures/<capture-id>/` paths. Add `control.json`, whose versioned body contains:

- Store UUID, nonnegative generation and at most one pending **complete Intent** (or null).
- Outcome totals; latest successful raw capture per fixture/live tram product; greatest retained live Retry-After deadline. These maps have fixed supported keys, not one entry per capture or session.
- SHA-256 of the body excluding the checksum field, serialized as UTF-8 JSON with sorted keys, compact separators, ASCII escaping and non-finite numbers forbidden. It detects accidental corruption, not malicious edits or an old valid checkpoint being restored.

Validate the schema, store identity, checksum and a 16 KiB serialized size limit before use. Start with generation zero, null pending and empty totals. Summary is a durable materialized count of finalized captures in this store, not proof that all historical bytes were re-read. No historical capture IDs or growing arrays belong in control.

`control.json` is the only mutable capture-accounting record. Publish a complete replacement through a same-directory temporary file, file fsync, atomic replace and containing-directory fsync while holding the OS lock. Published capture evidence remains create-only. Initialization publishes and synchronizes the empty control before publishing the v2 store marker last; an interrupted initialization never becomes an empty ready store implicitly. Temporary control files are not authoritative and must never be promoted merely because the published control is missing/corrupt.

`run` must refuse a missing, corrupt, wrong-store or unsupported control record; it does not rebuild it by scanning history. Restoring a backup means restoring a consistent stopped store, not copying an old control over newer captures. A valid rollback of only control cannot be detected by bounded startup alone; full verify compares it with retained evidence.

### Attempt ordering and exactly-once accounting

1. Require null pending. Allocate a new capture UUID and complete Intent, then durably replace control with that pending Intent and the next generation; totals remain unchanged. No provider request has started yet.
2. Create the capture directory and its identical immutable intent, synchronize them, and only then send one provider request. A pre-existing conflicting identity stops collection.
3. Retain response bytes/receipt and publish the terminal manifest under ADR 0016's ordering. Verify a successful response before accepting it. An HTTP retry is always a new capture after this attempt is finalized.
4. From the current pending Intent and validated terminal manifest, compute updated totals/last receipt/Retry-After and atomically publish **one** control replacement that both applies the summary contribution and clears pending. Advance generation once. Admit the next capture only after this publication is durable.

If publication fails, stop collection. The manifest may already be complete, but no subsequent request can race reconciliation. A repeated storage completion for a finalized capture may validate that specific capture and return its existing outcome; it never contributes to the summary again. No normal completion or retry enumerates the archive.

| Interruption / observed state | Recovery before the next request |
| --- | --- |
| Valid control with null pending | Read no capture history; use the stored summary and cooldown |
| Pending published, directory or intent absent | Re-create the reserved Intent from control, publish abandoned/interrupted, then finalize accounting; never fetch |
| Pending intent plus partial response staging only | Preserve staging, publish abandoned/interrupted and finalize accounting |
| Pending plus complete response, no manifest | Verify that response, reconstruct captured manifest and finalize accounting |
| Pending plus terminal manifest | Verify that one attempt and atomically apply its contribution while clearing pending |
| Crash during final control replace | Load either the old pending checkpoint or new idle checkpoint; old means finish once, new means it is already counted |
| Control, pending identity or published evidence conflicts/corrupts | Stop; preserve evidence; require operator investigation |

The synchronous writer admits no second pending capture. Thus normal startup reads a bounded checkpoint and at most one capture, including at most one 8 MiB payload. This describes the read set, not a promised wall-clock latency. Disk checks, mount checks and whole-run locking still apply. Existing 60-second live startup cooldown and greater persisted Retry-After survive without scanning historical manifests.

Session start/end records remain an audit trail. New starts take previous capture instants from control; normal startup never enumerates historical sessions. Orphan/unknown historical directories become verify findings rather than fast-status counts. Status must report historical orphan count as **not checked**, not zero.

### Fast status versus full verify

Proposed `run` and `status` acquire the existing exclusive lock, validate control and reconcile the pending slot. `status` reports `integrity_scope: checkpoint-and-pending`, summary counts and recovery result. It must not call this a fully verified store. A held lock remains ownership information, not proof of provider health. Corruption in a completed historical capture can remain undetected until full verify; this is an explicit trade-off requiring architect acceptance.

Proposed `verify` is a separate offline command holding the same lock, with no network. It streams through the archive, validates every published intent/receipt/manifest, hashes all published payloads and compares derived totals/last receipts/Retry-After with control. Exclude the active pending capture from finalized totals, even if its terminal manifest exists; validate its retained state against the pending Intent instead. A reserved pending Intent with no directory is a recognized interruption, not fabricated capture evidence. Unexpected directories or evidence outside this accounting model are findings. Inspection must not invent source timestamps, refetch or change any capture outcome.

For v2, before scanning, durably publish a bounded `verification-block.json` marker. `run` refuses this marker; `status` reports verification required. If scan fails or is interrupted, leave it in place. A complete successful verify publishes a bounded last-verification report (store UUID, control generation, UTC completion time, capture and payload-byte counts, verdict) and then removes/synchronizes the marker. Re-running verify after investigation is the only normal way to clear it. If the marker cannot be persisted, do not start the scan or report success. Verify reports problems but does not repair checkpoint or evidence. Inconsistent control cannot be certified from raw files by assuming a lost pending reservation never existed.

These report/block files are control metadata, not capture evidence. Their creation/publication/removal requires the same crash testing as control. Verify's archive-size cost and exclusive-lock pause are explicit. No background verification scheduler or retention deletion is included.

### Existing stores and rollback

Recommend **fresh v2 stores for this rollout**, with no in-place migration or deletion of v1 evidence. The operator stops/fences the old collector, retains the old store and its known image reference, chooses a new empty store path, initializes v2 explicitly and records the collection gap. Totals are per store; v1 history is retained separately and is not silently included in v2 status. This is a rollout proposal, not evidence that the operator has no existing captures.

New `run`/`status` refuse a v1 marker with a specific version error; they must not reinterpret v1 as an empty v2 store. Old images already reject the different v2 marker and must not be used against it. Under this proposal, the new `verify` path also accepts v1 for read-only inspection using its original full-scan semantics without reconciling or rewriting outcomes; incomplete intents are reported. The v2 block/report publication protocol does not modify a v1 store.

Rollback stops v2 and restores the matching image/store pair. Keep all v2 captures; switching back to a v1 store creates an explicitly recorded gap and does not copy newer control metadata backwards. A future requirement to aggregate or migrate old stores needs a separate reviewed operation.

## Implementation acceptance after approval

- Kill the Linux writer before/after pending publication, intent, response, manifest, the combined summary/pending replacement and its directory fsync; verify identical terminal outcome and exactly one summary contribution after repeated restarts. Include failed requests and a long Retry-After.
- Normal startup/status with zero pending opens no historical capture or session records. With one pending it hashes only that attempt. Instrument file access as well as measuring time; a warm OS cache is not evidence that a full scan was removed.
- Build small and substantially larger synthetic archives; report capture/file/byte counts, filesystem, code revision, runs and startup timings. No invented target latency or unmeasured throughput claim.
- Corrupt/delete control, restore an older valid control, alter a completed payload, create an unindexed directory and interrupt verify. Fast startup's limits must match the documented integrity scope; verify must detect archive/accounting discrepancies and leave collection blocked after failure/interruption.
- Verify all supported terminal outcomes, pending/no-directory cases, summary totals per mode/feed and failure metadata. Capture success remains distinct from source validity.
- Reject v1 from v2 run/status, preserve its bytes during read-only verify, reject partial initialization, and test old-image refusal of v2. Rehearse the explicit fresh-store/image rollback without deleting either store.
- Keep PR #51 safeguards: persistent-filesystem admission, no runtime test bypass, bounded request/retry behavior, non-root minimal image and no secrets in records/logs.

Once approved, update ADR 0016's current startup/verification wording as an explicit v2 amendment, implement these cases, then perform Ubuntu fixture/reboot acceptance. The live gate remains open until implementation and evidence pass; source-use, cadence/retention, uploader and external heartbeat decisions remain separate.

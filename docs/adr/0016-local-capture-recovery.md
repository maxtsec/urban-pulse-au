# ADR 0016: Local capture journal and recovery

Date: 2026-10-07

Status: **Accepted by the project architect on 2026-10-07: option A**. ADR 0015 accepts the Linux host and local raw tier; ADR 0003 explicitly leaves capture persistence/recovery for A-03. This decision selects that local format before implementing it. Source retention, operating cadence and live activation remain separate approvals.

## Options

| Option | Benefit | Cost |
| --- | --- | --- |
| A: Per-attempt immutable files (selected) | Direct byte inspection and export; no new database; implements the existing intent/payload/manifest proposal | Explicit filesystem synchronization, reconciliation and single-writer discipline |
| B: SQLite journal with payload files | Indexed backlog/history and transactional metadata | New database schema/migrations and coordination with separately persisted payload files |

## Decision: A

Use a versioned, collector-owned directory on one local Linux filesystem. Each upstream request has a fresh UUID capture ID, including retries after HTTP failure and identical successful bytes. A retry of a local storage operation reuses the existing ID. Capture identity is separate from payload SHA-256 and future domain revisions.

Initialize an explicit store marker before starting. Runtime refuses missing/wrong markers or unsuitable storage; it never silently creates a replacement data directory when a configured mount is missing. Runtime permits ext4/XFS/Btrfs only; tmpfs and container overlay are rejected even for fixtures. Ephemeral-storage testing uses injection in test code, not a runtime bypass. Hold an OS file lock for the whole run, including recovery. One local host is the ownership boundary; moving hosts requires stopping/fencing the old collector, transferring the store and recording the gap. A local lock does not coordinate two different disks or hosts.

Persist an intent before requesting a feed. A completed response is published as a single immutable response directory containing exact bytes and receipt metadata, then a terminal manifest is published. Temporary files/directories are on the same filesystem. Synchronize file contents and containing directories around publication; no overwrite of published records. Verify content hashes when an existing identity is encountered.

A capture-v1 intent records capture ID, fixture/live mode, endpoint alias, provider/product, request start and collector version. A response records request/receipt instants, HTTP status, content type/encoding, byte length/hash and a relative payload locator. A terminal manifest records one of captured, fetch-failed, raw-write-failed or abandoned, with a fixed reason and response metadata when available. Never persist keys, arbitrary exception text, credential-bearing URLs or request headers. Source time is null with reason not-yet-decoded; normalization later records verified source timestamps without rewriting capture evidence.

HTTP success with durably retained bytes means raw capture succeeded, not that source data is valid/current or normalization succeeded. A failed storage write does not advance successful capture. Malformed source content remains available for later validation/quarantine. Capture-only code does not publish city events or change application freshness.

| Interruption | Restart action |
| --- | --- |
| Intent only, including an incomplete response staging directory | Record abandoned; never invent received bytes or a success |
| Published response directory without manifest | Verify the complete response metadata/hash and finish the captured manifest |
| Manifest already present | Verify immutable evidence and leave the outcome unchanged |
| Corrupt/conflicting published evidence | Stop with a fixed integrity failure; preserve evidence for operator recovery |
| Failed HTTP request | Record fetch-failed; a later upstream retry gets a new capture ID |
| Raw storage failure | Record raw-write-failed if possible; otherwise restart reconciles unfinished intent; stop collection |

The first implementation stores uncompressed per-attempt bytes. Deduplication, compression, automatic deletion and normalized uploads remain separate reviewed changes. Until a retention policy and uploader exist, use an explicit disk reserve and stop when it is exhausted; do not run unattended indefinitely. Pending upload confirmation must eventually pin its source raw bytes as ADR 0015 requires.

## Live activation gate

The architect's review on 2026-10-07 keeps the current full-history scan for fixture acceptance and defers incremental recovery as mandatory work **before live activation**. That follow-up must select a durable pending index, reconcile only incomplete attempts on ordinary startup, and expose full payload verification separately. Preserve immutable capture evidence and test every index/publication interruption. No pending-index format or migration is accepted by this record; [ADR 0017](0017-incremental-capture-recovery.md) proposes that refinement for architect review before implementation.

## First implementation acceptance

- Synthetic HTTP responses produce retrievable exact bytes, matching hashes and immutable manifests; unchanged bytes still have separate capture IDs.
- Linux process-crash tests interrupt each publication boundary and recover without duplicate upstream fetches or invented success.
- Concurrent processes sharing the same store cannot both capture; missing mounts/markers, corruption and low disk fail closed.
- Shared per-process request budget includes retries; redirects never forward credentials; timeout/size limits, 429 Retry-After and server-error backoff are tested without live keys.
- Restart reconciles before polling; controlled shutdown releases the lock. Local status distinguishes a running process from successful captures and records restart/gap evidence.
- Ubuntu container packaging uses the existing pinned Python base, explicit source copies, a non-root user, a mounted data directory and a read-only secret file. No incoming ports or Google Cloud identity are needed for this local step.
- Source cadence, raw retention and continuous live enablement are reviewed before deployment to the operator host. Fixture acceptance can proceed independently.

Implementation and evidence status belong in the [delivery plan](../delivery-plan.md). GCS upload/verification and external heartbeat monitoring remain later CLOUD-01 work under [ADR 0015](0015-local-capture-collector.md).

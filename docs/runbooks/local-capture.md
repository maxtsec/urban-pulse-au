# Local capture on Ubuntu

[ADR 0016](../adr/0016-local-capture-recovery.md) selects the immutable file journal; [ADR 0017](../adr/0017-incremental-capture-recovery.md) adds v2 checkpoints, store-local capture sequences and offline verification. This runbook covers finite local acceptance; [delivery status](../delivery-plan.md) tracks the later uploader, monitoring and continuous operation gates.

## Host preparation

Use a supported Ubuntu release with Docker Engine, security updates, synchronized UTC time and local persistent storage. Keep host addresses, keys and hardware details in private operator notes. Disable sleep before any later unattended run. Do not use network shares, synchronized folders or a removable mount that can disappear under a running collector. The runtime accepts only ext4, XFS and Btrfs. It rejects tmpfs, overlay and other mount types for every command, including fixture init/run/status/verify. There is no CLI or environment switch to bypass the check. Stop the old collector before moving its store to another host.

Run the following Bash commands from a clean, reviewed repository checkout. Docker access and sudo are needed for image building and initial directory ownership; the collector itself uses UID/GID 10001. Choose a new, dedicated store on the intended filesystem, and verify the mount before initializing. `--mount` deliberately fails if the source directory is missing.

```bash
export CAPTURE_STORE=/srv/urbanpulse-capture/store-v2
findmnt -T /srv
sudo install -d -m 0700 -o 10001 -g 10001 "$CAPTURE_STORE"
docker build --target runtime -f workers/capture/Dockerfile   --build-arg COLLECTOR_VERSION="$(git rev-parse HEAD)"   -t urbanpulse-capture:local .

docker run --rm --network none --read-only --cap-drop ALL   --security-opt no-new-privileges   --mount "type=bind,src=$CAPTURE_STORE,dst=/data"   urbanpulse-capture:local init --store /data
```

Only initialize a new empty directory. Missing/invalid `store.json` during normal operation is an error, not permission to reinitialize. `init` refuses an unknown nonempty directory. Never remove the lock file to bypass a running collector: the OS releases the lock when the process exits.

The runtime installs only the locked `capture` dependency group (httpx, pydantic and their transitive dependencies). uv and pytest are confined to build/test stages; application/database/cloud dependencies are not installed.

## Offline acceptance

```bash
docker run --rm --name urbanpulse-capture-fixture   --network none --read-only --cap-drop ALL --security-opt no-new-privileges   --pids-limit 128 --memory 512m --stop-timeout 30   --mount "type=bind,src=$CAPTURE_STORE,dst=/data"   urbanpulse-capture:local run --store /data --max-attempts 6 --max-seconds 120

docker run --rm --network none --read-only --cap-drop ALL   --security-opt no-new-privileges   --mount "type=bind,src=$CAPTURE_STORE,dst=/data"   urbanpulse-capture:local status --store /data
```

On a new store, expect six captured attempts (two per tram feed), no failures, and separate capture IDs for identical bytes. Fixture bytes are deliberately labelled synthetic and are not claimed to be parseable GTFS-Realtime. No key, cloud identity, database, inbound port or network is required. Repeat the run: the earlier manifests remain unchanged and another six captures are retained.

`status` takes the exclusive lock, validates the bounded control checksum/identity and reconciles at most one unfinished capture. It reports `integrity_scope: checkpoint-and-pending`, outcome counts, last successful receipt per mode/feed, the retained live retry deadline, the next sequence and any interrupted/failed verification. `orphan_directories: null` means **not checked**, not zero. It does not enumerate historical captures or sessions and does not certify historical integrity. A previous full-verification report includes the generation/time it actually covered. While a collector runs, status reports `collector_already_running`; that proves ownership, not source health.

Full historical verification is explicit and offline. Stop the collector first:

```bash
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges \
  --mount "type=bind,src=$CAPTURE_STORE,dst=/data" \
  urbanpulse-capture:local verify --store /data
```

`verify` holds the same lock and reads all published capture metadata/payloads, checking hashes, accounting and sequences. It does not reconcile pending attempts or repair evidence. A missing reserved capture is reported incomplete without fabricating bytes. Unpublished staging bytes are retained for diagnosis and excluded from published-payload verification. The command is proportional to retained history and pauses collection while it owns the lock.

Before reading history, `verify` durably publishes `verification-in-progress.json`, which blocks collection. A killed process or reboot retains that hold: rerun full verify to completion before restarting the collector. If it finds damage, `verification-block.json` adds the fixed failure reason. If that diagnostic write fails (disk full/read-only), the existing hold still blocks `run`; `status` exits 2 with `verification_required`. Unexpected scan exceptions also retain the hold.

A controlled cancellation before any finding releases only a fresh scan's hold. Cancelling a retry of an interrupted/failed scan never releases its earlier hold. Run full verify in a planned maintenance window; after a reboot, the operator must complete it and record the collection gap. No automatic continuation/heartbeat is supplied here. Restore/investigate from a consistent backup, then rerun verify successfully; do not delete either marker to force collection.

`sessions/*.start.json` records each restart and the previous capture instants. A matching `.end.json` records controlled shutdown/result; its attempt count is null if execution failed before a final count was returned. Capture manifests remain the per-attempt evidence. An unmatched start means an unclean exit; capture timestamps bound the observable gap without claiming its exact cause or duration. No external heartbeat or alert is provided by this slice.

## Storage and recovery

```text
store.json                       # capture-store-v2 and store UUID
control.json                     # checksummed pending + summary + next sequence
by-sequence/<19-digit-sequence>   # create-only store/sequence/capture UUID mapping
.collector.lock
staging/                         # unpublished intent/reconstruction metadata
verification-in-progress.json     # blocks collection during/after interrupted inspection
verification-block.json           # only after a recorded finding/error
last-verification.json            # most recent completed full inspection
captures/<capture-uuid>/
  intent.json
  response/payload.bin
  response/receipt.json
  manifest.json
sessions/<session-uuid>.start.json
sessions/<session-uuid>.end.json
```

Store-local `capture_sequence`, mode, product, request/receipt times and version are in the immutable records, rather than encoded in the directory name. Raw bytes, SHA-256 and length are verified together. Source observation time remains null with `not-yet-decoded`; a captured response does not establish valid/current transport data.

A sequence and complete pending intent are reserved in control before publishing intent or issuing a request. Failed and abandoned captures consume their sequence; recovery never reuses it. Each new store starts at 1 with a different store UUID. Sequence is ordering, not successful processing/upload acknowledgement. `by-sequence/0000000000000000001` directly identifies capture 1 without enumerating UUID directories. The index is durable before a provider request starts; recovery reconciles only the pending index. The adapter's `capture_at_sequence` validates the specific index/intent and exposes only finalized captures. Missing finalized mappings fail explicitly; `verify` checks all mappings against retained captures.

The response directory is published atomically before the terminal manifest. A reserved capture without a published intent becomes `abandoned/not_started`; its reconstructed intent and manifest are published together. A published intent without a response becomes `abandoned/interrupted`, because a request might have started. A complete retained response can finish its missing manifest. Finally, one atomic control replacement updates totals and clears pending. Repeating recovery does not count a capture twice. Generated failure/abandonment completion times are floored at the request intent time, avoiding impossible ordering after NTP clock rollback; successful receipt/source timestamps are not rewritten. Temporary files are preserved for diagnosis; published outcomes never change.

On corruption, stop and preserve the store. Work from a backup when investigating; do not edit manifests to make verification pass. Collection stops before a request when free space falls below the 256 MiB reserve plus the maximum 8 MiB response and metadata headroom. This is not retention: nothing is automatically deleted, compressed or deduplicated. Pending-upload bytes must later be pinned under ADR 0015. Copy a stopped store for a consistent backup; a single disk remains a single failure boundary.

## V1 stores and rollback

Keep v1 evidence and its pinned known-working image. Stop/fence that collector, back up its stopped store, initialize a **new empty v2 path**, record the gap and run fixtures before any approved live rollout. There is no in-place migration or automatic aggregation. Earlier unreleased v2 test stores without the sequence index also require a new path; do not mix review-test images or manufacture an empty index over retained captures. V2 `run`/`status` reject v1 with `store_version_requires_fresh_v2`; old images reject v2. New `verify` can inspect v1 read-only and reports unfinished captures rather than completing them. It does not add v2 control or verification records to v1.

Rollback means stop v2 and restore the matching v1 image/store pair. Preserve all newer v2 evidence; do not copy a v1 marker/control into v2 or restore an old control checkpoint over newer captures. Normal startup cannot detect an otherwise valid old checkpoint; full verify detects discrepancies with retained capture sequences and totals. Downstream cursors must include store UUID and processing version; per-object upload confirmation remains separate.

## Bounded live operation gate

The runtime has an explicit `--live --key-file /run/secrets/transport-key` mode, but this PR neither authorizes nor executes it. Before any live activation, review the v2 recovery/verification implementation and its evidence, complete Ubuntu fixture/reboot acceptance, and accept source-use/local retention, a measurement plan and operating cadence. Use a separate live store, stop any other probe using the same provider quota, and mount a plain-text key file read-only, outside the repository/image. Set its host ownership to 10001 and permissions to 0400. Do not supply the key as a CLI value, image build argument or environment variable. Only live mode needs outbound provider HTTPS/DNS; it still needs no inbound ports or Google identity.

Both modes require finite bounds (defaults: six attempts, 120 seconds; maxima: 120 attempts, 3600 seconds). Live mode first waits at least 60 seconds after taking ownership, then spaces all requests/retries by at least 15 seconds. Feeds rotate after success; errors retry that feed with bounded exponential delay, honoring longer Retry-After values. Persisted Retry-After deadlines survive restarts. This conservative shared budget is a safety ceiling, **not the approved production cadence** or proof of provider quota scope. Recovery never refetches an old attempt. Every new upstream request gets a new capture ID.

401/403, redirects and other non-retryable HTTP rejections stop the run. Body-transfer network errors, elapsed-time/size limits and unexpected encoding take the bounded retry/backoff path even when response headers said HTTP 200; partial bodies are never published. Request failures retain only fixed reason/status metadata; error bodies and arbitrary headers are not stored. Successful identity-encoded responses retain exact bytes (including malformed content); decoding belongs to a later normalizer. Unexpected content encodings fail explicitly. HTTP operation timeout is ten seconds, with a fifteen-second elapsed check at each body chunk and an 8 MiB ceiling. The run duration limits admission of new requests; an in-flight fetch and durable write finish before shutdown. SIGTERM interrupts waits and prevents the next request; allow thirty seconds for an in-flight operation.

Exit 0 means the finite run completed without request failures, or stopped on request; 1 means request failures/no captures within the allotted duration; 2 means configuration, storage, lock or integrity failure. Review the JSON counts and manifests, not exit status alone.

Do not add an automatic restart loop, timer or always-on service yet. Continuous cadence, retention, disk monitoring and upload/heartbeat behavior need their own acceptance before unattended operation.

## Reproduce Linux acceptance

```bash
docker build --target test -f workers/capture/Dockerfile -t urbanpulse-capture:test .
docker run --rm --network none --read-only   --tmpfs /tmp:rw,nosuid,nodev,size=512m   --cap-drop ALL --security-opt no-new-privileges   --pids-limit 128 --memory 512m urbanpulse-capture:test
```

The same command runs in CI. Filesystem/process tests explicitly inject a test filesystem check for their disposable tmpfs store. The test helper is absent from the runtime image; unmodified CLI subprocess tests also assert real tmpfs rejection. Separate runtime-image acceptance uses a persistent Docker volume. Tests terminate child processes at journal publication boundaries and verify recovery, exclusive ownership, immutable retry, low disk, corruption, signals and real CLI output. Process termination verifies Linux filesystem behavior; it is not a physical power-loss or host-disk durability certification. The [Ubuntu rehearsal record](../evidence/cloud-01-ubuntu-acceptance.md) contains a completed representative-host reboot drill and reproducible steps. Verify dedicated, always-on operation and the remaining ADR 0015 host requirements before live deployment. Repeat host acceptance when moving stores/hosts or changing persistence behavior.

## Accepted tram schedule

Live finite runs automatically use positions every 60 seconds, updates every 120 seconds and alerts every 60 seconds. All starts share the minimum 15-second spacing and persisted Retry-After guard. A slot tolerates less than 15 seconds of wakeup/publication delay; older missed slots are skipped. Independent feed backoff preserves healthy-feed progress. No second collector or probe may spend the same subscription budget.

For an offline rehearsal, append `--tram-schedule --max-attempts 5 --max-seconds 115` to the existing fixture `run` command. This takes real elapsed time and reaches slots 0, 15, 30, 60 and 90; it does not contact the provider. Live retains the 60-second startup cooldown, so its first five healthy slots need a duration exceeding 150 seconds. `--interval` can slow the minimum spacing but cannot accelerate live cadence. Ordinary fixture tests retain their fast default loop.

This schedule does not start unattended operation or change the v2 store. [ADR 0018](../adr/0018-capture-delivery-and-expiry.md) records the accepted fresh-v3 expiry mechanism, separate raw-duration decision and accepted B metadata confirmation and manual unlock.

## Explicit v3 fixture rehearsal

The [v3 format](../architecture/capture-store-v3.md) requires a new empty directory on a supported persistent Linux filesystem. Preserve the existing v2 store and its image. Use the same hardened Docker invocation and mount from the earlier examples, appending `--store-version v3` to **each** `init`, `run`, `status` and `verify` command. Omitting it still selects v2 and refuses a v3 marker. Fixture mode remains the default.

Start with finite fixture capture; `verify` reports retained/expired bytes separately. No command in this release writes expiry records or deletes raw. Never hand-author expiry/confirmation evidence to unblock a failed scan. If synthetic future-expiry evidence is incomplete, verify retains a hold and reports `recovery_required`; preserve the store for inspection. The future reviewed expiry writer is required to finish such an operation.

Do not point the v3 initializer at a v2 archive, manually change a marker, or reuse a partial initialization directory after a crash. Inspect and retain the old directory, then initialize a fresh empty one. Real normalized output, cloud acknowledgement and raw expiry remain later acceptance steps.

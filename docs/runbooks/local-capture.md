# Local capture on Ubuntu

[ADR 0016](../adr/0016-local-capture-recovery.md) selects the immutable file journal. This runbook covers finite local acceptance; [delivery status](../delivery-plan.md) tracks the later uploader, monitoring and continuous operation gates.

## Host preparation

Use a supported Ubuntu release with Docker Engine, security updates, synchronized UTC time and local persistent storage. Keep host addresses, keys and hardware details in private operator notes. Disable sleep before any later unattended run. Do not use network shares, synchronized folders or a removable mount that can disappear under a running collector. The adapter accepts ext4, XFS and Btrfs, plus tmpfs/overlay for container acceptance; use persistent local storage for retained captures. It refuses other mount types. Stop the old collector before moving its store to another host.

Run the following Bash commands from a clean, reviewed repository checkout. Docker access and sudo are needed for image building and initial directory ownership; the collector itself uses UID/GID 10001. Choose a new, dedicated store on the intended filesystem, and verify the mount before initializing. `--mount` deliberately fails if the source directory is missing.

```bash
export CAPTURE_STORE=/srv/urbanpulse-capture/store
findmnt -T /srv
sudo install -d -m 0700 -o 10001 -g 10001 "$CAPTURE_STORE"
docker build --target runtime -f workers/capture/Dockerfile   --build-arg COLLECTOR_VERSION="$(git rev-parse HEAD)"   -t urbanpulse-capture:local .

docker run --rm --network none --read-only --cap-drop ALL   --security-opt no-new-privileges   --mount "type=bind,src=$CAPTURE_STORE,dst=/data"   urbanpulse-capture:local init --store /data
```

Only initialize a new empty directory. Missing/invalid `store.json` during normal operation is an error, not permission to reinitialize. `init` refuses an unknown nonempty directory. Never remove the lock file to bypass a running collector: the OS releases the lock when the process exits.

## Offline acceptance

```bash
docker run --rm --name urbanpulse-capture-fixture   --network none --read-only --cap-drop ALL --security-opt no-new-privileges   --pids-limit 128 --memory 512m --stop-timeout 30   --mount "type=bind,src=$CAPTURE_STORE,dst=/data"   urbanpulse-capture:local run --store /data --max-attempts 6 --max-seconds 120

docker run --rm --network none --read-only --cap-drop ALL   --security-opt no-new-privileges   --mount "type=bind,src=$CAPTURE_STORE,dst=/data"   urbanpulse-capture:local status --store /data
```

On a new store, expect six captured attempts (two per tram feed), no failures, and separate capture IDs for identical bytes. Fixture bytes are deliberately labelled synthetic and are not claimed to be parseable GTFS-Realtime. No key, cloud identity, database, inbound port or network is required. Repeat the run: the earlier manifests remain unchanged and another six captures are retained.

`status` takes the exclusive lock, reconciles unfinished attempts and verifies every stored payload hash. It returns outcome counts, the last successful raw capture per mode/feed, unresolved pre-intent directories and any retained live retry deadline. While a collector runs it reports `collector_already_running`; that proves ownership, not source health. Stop the finite collector before a full status scan. Scanning is proportional to retained files/bytes and is intentionally not a frequent health probe.

`sessions/*.start.json` records each restart and the previous capture instants. A matching `.end.json` records controlled shutdown/result; its attempt count is null if execution failed before a final count was returned. Capture manifests remain the per-attempt evidence. An unmatched start means an unclean exit; capture timestamps bound the observable gap without claiming its exact cause or duration. No external heartbeat or alert is provided by this slice.

## Storage and recovery

```text
store.json
.collector.lock
captures/<capture-uuid>/
  intent.json
  response/payload.bin
  response/receipt.json
  manifest.json
sessions/<session-uuid>.start.json
sessions/<session-uuid>.end.json
```

Mode, product, request/receipt times and version are in the immutable records, rather than encoded in the directory name. Raw bytes, SHA-256 and length are verified together. Source observation time remains null with `not-yet-decoded`; a captured response does not establish valid/current transport data.

The response directory is published atomically before the terminal manifest. An intent without a published response becomes abandoned; a complete retained response can finish its missing manifest. Temporary files and pre-intent directories are preserved for diagnosis. A published terminal outcome cannot change, including after a late storage retry.

On corruption, stop and preserve the store. Work from a backup when investigating; do not edit manifests to make verification pass. Collection stops before a request when free space falls below the 256 MiB reserve plus the maximum 8 MiB response and metadata headroom. This is not retention: nothing is automatically deleted, compressed or deduplicated. Pending-upload bytes must later be pinned under ADR 0015. Copy a stopped store for a consistent backup; a single disk remains a single failure boundary.

## Bounded live operation gate

The runtime has an explicit `--live --key-file /run/secrets/transport-key` mode, but this PR neither authorizes nor executes it. First accept source-use/local retention, a measurement plan and operating cadence. Use a separate live store, stop any other probe using the same provider quota, and mount a plain-text key file read-only, outside the repository/image. Set its host ownership to 10001 and permissions to 0400. Do not supply the key as a CLI value, image build argument or environment variable. Only live mode needs outbound provider HTTPS/DNS; it still needs no inbound ports or Google identity.

Both modes require finite bounds (defaults: six attempts, 120 seconds; maxima: 120 attempts, 3600 seconds). Live mode first waits at least 60 seconds after taking ownership, then spaces all requests/retries by at least 15 seconds. Feeds rotate after success; errors retry that feed with bounded exponential delay, honoring longer Retry-After values. Persisted Retry-After deadlines survive restarts. This conservative shared budget is a safety ceiling, **not the approved production cadence** or proof of provider quota scope. Recovery never refetches an old attempt. Every new upstream request gets a new capture ID.

401/403, redirects and other non-retryable responses stop the run. Request failures retain only fixed reason/status metadata; error bodies and arbitrary headers are not stored. Successful identity-encoded responses retain exact bytes (including malformed content); decoding belongs to a later normalizer. Unexpected content encodings fail explicitly. HTTP operation timeout is ten seconds, with a fifteen-second elapsed check at each body chunk and an 8 MiB ceiling. The run duration limits admission of new requests; an in-flight fetch and durable write finish before shutdown. SIGTERM interrupts waits and prevents the next request; allow thirty seconds for an in-flight operation.

Exit 0 means the finite run completed without request failures, or stopped on request; 1 means request failures/no captures within the allotted duration; 2 means configuration, storage, lock or integrity failure. Review the JSON counts and manifests, not exit status alone.

Do not add an automatic restart loop, timer or always-on service yet. Continuous cadence, retention, disk monitoring and upload/heartbeat behavior need their own acceptance before unattended operation.

## Reproduce Linux acceptance

```bash
docker build --target test -f workers/capture/Dockerfile -t urbanpulse-capture:test .
docker run --rm --network none --read-only   --tmpfs /tmp:rw,nosuid,nodev,size=512m   --cap-drop ALL --security-opt no-new-privileges   --pids-limit 128 --memory 512m urbanpulse-capture:test
```

The same command runs in CI. Tests terminate child processes at journal publication boundaries and verify recovery, exclusive ownership, immutable retry, low disk, corruption, signals and real CLI output. Process termination verifies Linux filesystem behavior; it is not a physical power-loss or host-disk durability certification. Actual Ubuntu host setup and a reboot drill remain operator deployment checks.

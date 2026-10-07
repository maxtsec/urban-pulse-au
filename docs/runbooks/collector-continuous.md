# Continuous capture and heartbeat client

This service uses the accepted 60/120/60-second tram schedule in one long-lived process. It keeps feed backoff, shared spacing and Retry-After state across polls; a process restart also observes the persisted cooldown and live startup delay. Missed slots are skipped. `run` remains the finite rehearsal command; `serve` requires an existing v3 store and does not initialize it.

## Process and daemon recovery

The host supervisor runs independently of `docker.service`. It waits 60 seconds between failed launches or daemon checks, then repeats the encrypted-volume/configuration guard before reconnecting or launching. Docker/containerd package restarts therefore do not stop the supervisor. With Docker live-restore, it attaches to the existing owned container; otherwise it starts one replacement. The exclusive store lock remains the final single-writer guard.

An existing container must have the exact name, owner label, immutable image ID and expected fixture/live command. A stopped owned container can be removed without force. An ownership/mode mismatch refuses automatic adoption; inspect it before cleanup. Permanent HTTP source rejection or a byte/inode reserve breach exits 78 and requires operator intervention. The supervisor and systemd do not automatically restart this state.

The systemd unit binds to the encrypted mount, not Docker. Mount stop/shutdown stops the service; a missing/wrong/locked volume refuses launch. `Restart=on-failure` restarts a crashed supervisor, while a deliberate `systemctl stop` remains stopped. There is no boot target or persistent desired-run flag: after reboot, manually unlock, mount and start. Root/Docker administrators remain trusted.

On stop, the supervisor stops the owned container before exiting; capture handles SIGTERM between bounded requests and commits its session outcome. An unconfirmed Docker stop is logged. Do not close/unmount the encrypted volume until Docker is reachable and the container is confirmed absent. Never force or lazy-unmount it.

## Resource protection

The container is capped at 512 MiB RAM with no additional swap allowance, 128 processes, read-only root, dropped capabilities, no core dumps and rotated local logs. The host supervisor has its own 192 MiB/64-task ceiling. These are initial safety ceilings, not measured production sizing; record peak memory and OOM/restart outcomes during host acceptance.

Before opening a session and before each capture, check bytes available to the unprivileged writer and free inodes. The byte floor is 256 MiB plus the maximum 8 MiB payload and 64 KiB write allowance. The inode floor is 4,096 plus 32 for an in-flight capture and cleanup. The worker exposes `--reserve-bytes`/`--reserve-inodes` to increase floors; lower values are rejected. A failed capacity read or either exhausted floor stops capture before reserving a sequence or issuing a request. A reserve breach emits a best-effort observation through the selected sink with `disk_reserve_reached` or `inode_reserve_reached` and exits 78. If detected at startup, no session is created; if detected while collecting, the existing session is closed once. Repeated start attempts while capacity remains low create no new session files. After repairing capacity, inspect status and explicitly start the service again. Pending-capture recovery still precedes the session check so reserved space remains available for durable recovery. This layer never deletes raw or metadata. Configure capacity/alert policy from actual allocation measurements before live activation.

## Dry-run heartbeat semantics

`serve` emits one local JSON heartbeat at startup, at most every 30 seconds during waits, and on graceful exit. It reads bounded in-memory checkpoint summaries, not capture history. Records contain a random process-session ID, mode, process state, emission time, monotonic uptime, per-feed last durable success, outcomes observed in this session, free bytes/inodes and a saturated send-failure count. No host address, filesystem path, credential or payload is included. Empty session outcomes mean no outcome observed since restart; `running` only means loop liveness, not healthy/fresh provider data.

The client has an injected sink: stdout dry-run by default, or the explicitly configured authenticated Monitoring exporter below. A failed send is counted; it cannot terminate capture or change committed outcomes. There is no retry queue. Pulses run on the collection thread, including long Retry-After waits; a hung fetch/write produces a heartbeat gap instead of an independent healthy pulse. Docker logs are bounded by the launcher. The Monitoring adapter bounds collection-thread waiting and preserves failure isolation.

**Dry-run output is not an external heartbeat or alert.** CLOUD-01 Terraform and its transport integration must establish the destination, authentication, missing-heartbeat/stalled-capture thresholds, redaction and alert delivery. In particular, a stopped daemon, locked host, full disk, power loss or killed process cannot reliably send a final failure record. External absence detection is a live-activation gate. No new cloud permissions are granted by this service.

## Authenticated raw-only exporter

After separately approved key installation and source acceptance, configure the supervisor with all three options:

~~~bash
/usr/bin/python3 -m scripts.collector_service --live \
  --monitoring-project EXAMPLE_PROJECT_ID --monitoring-collector EXAMPLE_LOGICAL_ALIAS
~~~

Use the reviewed private project ID and stable alias from Terraform's `monitored_resource` output. This is the `ExecStart` command for an operator-reviewed override, not an instruction to activate live collection before its gates pass. The supervisor validates both key files on the same encrypted mount: regular files, UID/GID 10001, mode 0600, no symlink/shadow mount. It binds only the DTP key and `/srv/urbanpulse/keys/collector-upload.json` read-only; the latter is capped at 16 KiB. Never put credential contents in unit arguments or logs. Existing-container adoption requires the same telemetry project/alias as well as the same image and mode.

The equivalent image options are `--monitoring-project`, `--monitoring-collector` and `--monitoring-key-file /run/collector-upload.json`, together with `serve --live`. Partial options, malformed targets or fixture export are rejected before store access. Omitting the options keeps local dry-run behavior. No SDK application-default credential discovery, gcloud login or metadata-server fallback occurs.

The exporter signs its assertion with `google-auth` and exchanges it at Google's fixed OAuth endpoint using only the `monitoring.write` scope. Tokens stay in memory and refresh before expiry; 401 discards the cached token for the next pulse. Requests use TLS verification, ignore proxy environment variables and do not follow redirects. The next refresh rereads the key; after an atomic host-file replacement, recreate the read-only bind/container through the normal guarded stop/start sequence before expecting the replacement inode to be visible.

Each running live pulse sends `heartbeat=1`, free bytes/inodes, and exactly three `capture_success_known` streams. It adds each `capture_age_seconds` only if a durable successful live receipt exists. A restart reads the existing bounded checkpoint summary; failed attempts and session restarts cannot reset successful-capture ages. Final/error pulses send available capacity/known/age values without prolonging heartbeat. No upload metric is emitted until an uploader can supply authoritative progress.

The batch contains 6-9 points while running (5-8 on exit), with only the fixed resource/feed labels from ADR 0019. Unknown ages remain absent. Fixture points, future successes and invalid/backwards pulse clocks are refused. Attempts are spaced by at least five seconds in both monotonic and wall time; forced closer pulses are dropped. Within a process, attempted timestamps are never replayed. Across restarts the collector preserves source-success timestamps; Monitoring's newer-point check remains authoritative for already accepted telemetry. Clock trouble is a telemetry gap, not fabricated healthy data.

OAuth plus publication share a five-second asynchronous I/O budget, with a 64 KiB response limit. The collection thread also stops waiting after five seconds even if operating-system resolver cleanup stalls. Only one export may remain in flight, with no queue or overlapping replacement: subsequent pulses report `previous_delivery_pending` until it finishes. A timed-out write may have reached Google and remains unconfirmed. Host shutdown retains the supervisor's bounded container-stop behavior.

Only HTTP 200 with the documented empty object confirms the whole batch. A rejected, partial, malformed or timed-out response records a fixed status plus the local metric/feed inventory under `unconfirmed`. It never logs provider bodies, credentials or resource identifiers. Do not retry that timestamp; inspect stream arrival separately and use the next genuine pulse. Send failures increment the local observation counter without terminating capture. A sent log confirms API acceptance, not alert delivery or healthy sources.

See the [Monitoring write API](https://docs.cloud.google.com/monitoring/api/ref_v3/rest/v3/projects.timeSeries/create) and [service-account OAuth protocol](https://developers.google.com/identity/protocols/oauth2/service-account) for the transport boundary. Complete the [enrollment and loss drill](capture-infrastructure.md#monitoring-enrollment-and-loss-drill) before enabling unattended collection. Raw-only enrollment concerns heartbeat, capture and capacity; upload remains disabled. The exporter cannot create descriptors, change alert policies or enable notification channels.

## Install and fixture drill

Complete the separately approved [encrypted-host setup](collector-encrypted-host.md) first. Use the reviewed runtime image ID in the existing private host configuration. Stop the finite rehearsal before starting this service.

```bash
sudo install -d -m 0755 /usr/local/lib/urbanpulse/scripts
sudo install -m 0644 scripts/collector_host.py scripts/collector_service.py /usr/local/lib/urbanpulse/scripts/
sudo install -m 0644 ops/collector/urbanpulse-capture.service /etc/systemd/system/
sudo systemd-analyze verify --man=no /etc/systemd/system/urbanpulse-capture.service
sudo systemctl daemon-reload
sudo systemctl start urbanpulse-capture.service
sudo journalctl -u urbanpulse-capture.service -f
```

Default launch is synthetic, with network disabled and no keys. Stop with `sudo systemctl stop urbanpulse-capture.service`. The command-line entry point inside the image is `serve --store /data --store-version v3`; the host guard remains mandatory for the installed service.

On an approved disposable/collector host, using fixture data:

1. Let all three feeds complete more than one cycle. Confirm continuing sequence progress and dry-run heartbeat timestamps; restart once and verify retained history.
2. Kill the capture process; expect bounded restart and the same store. Kill the supervisor; systemd must restart it and safely adopt or replace the owned container.
3. Stop Docker, wait through at least two retries, then start it. Repeat with `restart`, including the package-update equivalent. Expect one writer, a recorded capture gap and automatic recovery while the volume remains valid. Also test Docker live-restore if enabled.
4. Deliberately stop the service, then restart Docker. The service must stay stopped. Unlocking alone must not start capture.
5. Stop service/mount and lock the volume. Start attempts must refuse without a container or underlying-root files. Test a wrong configured volume identity as in the encrypted-host drill.
6. On a disposable test store/filesystem, exceed the configured byte and inode reserves separately. Confirm exit 78, no automatic restart, no new request/sequence and no deletion. Repeat startup three times while below reserve: no new session files should appear and the heartbeat should report the reserve reason. After capacity repair, explicitly start and confirm progress. Do not fill the real host disk to run this test.
7. Exercise missing-heartbeat/stalled-progress alert delivery with the authenticated exporter; dry-run sink-failure tests alone do not satisfy this gate.

Only after remaining live gates are approved, place the provider key in the encrypted volume at `/srv/urbanpulse/keys/transport-victoria` (regular file, UID/GID 10001, mode 0600, no symlink or shadow mount). An explicit systemd override can replace ExecStart with `/usr/bin/python3 -m scripts.collector_service --live`. It enables bridge networking and a read-only key bind; never put the key in a unit, command argument, image or repository. Install the reviewed override only during separately approved live activation.

## Validation scope

Exporter tests use ephemeral RSA keys and fake HTTP, verify signed scope/claims, raw-only stream semantics, restart history, unknown states, clock regression, forced-pulse spacing, token refresh, partial/error responses, redirects, response limits, network/DNS-cleanup deadlines and failure isolation. The isolated Linux image also exercises the real live CLI wiring against a disposable v3 store with synthetic source and HTTP boundaries. Host tests check encrypted key guards and adoption identity. These tests make no cloud calls and do not establish actual IAM, Monitoring arrival, notification or source acceptance.


Automated tests cover two hours of deterministic continuous scheduling beyond finite limits, Retry-After heartbeat progress, byte/inode refusal before requests, telemetry exceptions, real Linux CLI kill/restart/SIGTERM and v3 verification, Docker outage/recovery decisions, live-restore adoption, permanent rejection and manual stop. Docker lifecycle tests replace the daemon boundary; they do not certify real systemd ordering, LUKS mount loss or package updates. Complete the fixture host drill above and record private operator evidence before live activation. See [delivery plan](../delivery-plan.md) for current status.

Development checks on 2026-10-08: the isolated capture image passed 219 Linux tests; the updated read-only checkout passed 71 focused Linux runtime/host/scheduling tests. Ruff and both mypy scopes passed. The systemd unit passed syntax verification in a disposable container; this was not a running systemd/Docker integration drill.

Reserve regression validation: 75 focused Linux tests passed, including startup and in-session exhaustion for both resources. With the unmodified runtime image on a disposable v3 volume, three starts for each reserve returned 78, emitted the matching heartbeat reason, added zero sessions/captures and preserved every stored file hash; full v3 verification then passed. The temporary volume was removed.

# Continuous capture and heartbeat client

This service uses the accepted 60/120/60-second tram schedule in one long-lived process. It keeps feed backoff, shared spacing and Retry-After state across polls; a process restart also observes the persisted cooldown and live startup delay. Missed slots are skipped. `run` remains the finite rehearsal command; `serve` requires an existing v3 store and does not initialize it.

## Process and daemon recovery

The host supervisor runs independently of `docker.service`. It waits 60 seconds between failed launches or daemon checks, then repeats the encrypted-volume/configuration guard before reconnecting or launching. Docker/containerd package restarts therefore do not stop the supervisor. With Docker live-restore, it attaches to the existing owned container; otherwise it starts one replacement. The exclusive store lock remains the final single-writer guard.

An existing container must have the exact name, owner label, immutable image ID and expected fixture/live command. A stopped owned container can be removed without force. An ownership/mode mismatch refuses automatic adoption; inspect it before cleanup. Permanent HTTP source rejection exits 78 and requires operator intervention rather than repeatedly trying rejected credentials.

The systemd unit binds to the encrypted mount, not Docker. Mount stop/shutdown stops the service; a missing/wrong/locked volume refuses launch. `Restart=on-failure` restarts a crashed supervisor, while a deliberate `systemctl stop` remains stopped. There is no boot target or persistent desired-run flag: after reboot, manually unlock, mount and start. Root/Docker administrators remain trusted.

On stop, the supervisor stops the owned container before exiting; capture handles SIGTERM between bounded requests and commits its session outcome. An unconfirmed Docker stop is logged. Do not close/unmount the encrypted volume until Docker is reachable and the container is confirmed absent. Never force or lazy-unmount it.

## Resource protection

The container is capped at 512 MiB RAM with no additional swap allowance, 128 processes, read-only root, dropped capabilities, no core dumps and rotated local logs. The host supervisor has its own 192 MiB/64-task ceiling. These are initial safety ceilings, not measured production sizing; record peak memory and OOM/restart outcomes during host acceptance.

Before each capture, check bytes available to the unprivileged writer and free inodes. The byte floor is 256 MiB plus the maximum 8 MiB payload and 64 KiB write allowance. The inode floor is 4,096 plus 32 for an in-flight capture and cleanup. The worker exposes `--reserve-bytes`/`--reserve-inodes` to increase floors; lower values are rejected. A failed capacity read or either exhausted floor stops capture before reserving a sequence or issuing a request. The supervisor retries at a bounded rate, allowing recovery after operator repair. This layer never deletes raw or metadata. Configure capacity/alert policy from actual allocation measurements before live activation.

## Dry-run heartbeat semantics

`serve` emits one local JSON heartbeat at startup, at most every 30 seconds during waits, and on graceful exit. It reads bounded in-memory checkpoint summaries, not capture history. Records contain a random process-session ID, mode, process state, emission time, monotonic uptime, per-feed last durable success, outcomes observed in this session, free bytes/inodes and a saturated send-failure count. No host address, filesystem path, credential or payload is included. Empty session outcomes mean no outcome observed since restart; `running` only means loop liveness, not healthy/fresh provider data.

The client has an injected sink, with stdout dry-run as the only shipped adapter. A failed send is counted; it cannot terminate capture or change committed outcomes. There is no retry queue. Pulses run on the collection thread, including long Retry-After waits; a hung fetch/write produces a heartbeat gap instead of an independent healthy pulse. Docker logs are bounded by the launcher. The later cloud adapter must have bounded network timeouts and preserve failure isolation.

**Dry-run output is not an external heartbeat or alert.** CLOUD-01 Terraform and its transport integration must establish the destination, authentication, missing-heartbeat/stalled-capture thresholds, redaction and alert delivery. In particular, a stopped daemon, locked host, full disk, power loss or killed process cannot reliably send a final failure record. External absence detection is a live-activation gate. No new cloud permissions are granted by this service.

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
6. On a disposable test store/filesystem, exceed the configured byte and inode reserves separately. Confirm no new request/sequence, no deletion and successful recovery only after capacity repair. Do not fill the real host disk to run this test.
7. Exercise missing-heartbeat/stalled-progress alert delivery after the cloud adapter is available; dry-run sink-failure tests alone do not satisfy this gate.

Only after remaining live gates are approved, place the provider key in the encrypted volume at `/srv/urbanpulse/keys/transport-victoria` (regular file, UID/GID 10001, mode 0600, no symlink or shadow mount). An explicit systemd override can replace ExecStart with `/usr/bin/python3 -m scripts.collector_service --live`. It enables bridge networking and a read-only key bind; never put the key in a unit, command argument, image or repository. No live override or host provisioning is performed by this PR.

## Validation scope

Automated tests cover two hours of deterministic continuous scheduling beyond finite limits, Retry-After heartbeat progress, byte/inode refusal before requests, telemetry exceptions, real Linux CLI kill/restart/SIGTERM and v3 verification, Docker outage/recovery decisions, live-restore adoption, permanent rejection and manual stop. Docker lifecycle tests replace the daemon boundary; they do not certify real systemd ordering, LUKS mount loss or package updates. Complete the fixture host drill above and record private operator evidence before live activation. See [delivery plan](../delivery-plan.md) for current status.

Development checks on 2026-10-08: the isolated capture image passed 219 Linux tests; the updated read-only checkout passed 71 focused Linux runtime/host/scheduling tests. Ruff and both mypy scopes passed. The systemd unit passed syntax verification in a disposable container; this was not a running systemd/Docker integration drill.

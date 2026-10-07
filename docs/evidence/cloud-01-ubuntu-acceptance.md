# CLOUD-01 Ubuntu host rehearsal

The [local capture runbook](../runbooks/local-capture.md) defines the operating procedure; [ADR 0017](../adr/0017-incremental-capture-recovery.md) defines recovery. This record covers the runtime built from `96f8de2baaed5870d0b896c314bbba7f6165bc42` on 2026-10-07. Source was exported from that committed tree, without local files or credentials.

## Environment and scope

Supported Ubuntu LTS, Docker Engine, local ext4 storage and synchronized time. Exact host versions remain in private operator records. This is a representative host rehearsal; dedicated, always-on operation and the remaining ADR 0015 host requirements have not been fully verified. Runtime commands used UID/GID 10001, a read-only root, dropped capabilities, `no-new-privileges`, no network, no inbound ports, a 512 MiB memory limit and a fresh v2 bind-mounted store. A separate one-time ownership setup was needed for that directory. Private operator records retain host paths, logs and per-file hashes.

The locally built image has manifest-list digest `sha256:5ffb98339ad89e48afa7a6ff95fe24da3085d242fba3d29bc0ba0a413a43882b`; its runtime manifest is `sha256:c177fbdb1411c0726f0040b4d883f85dc143a70916861347c3aa4315b7a6a260`. These identify the local build, not a published registry image.

## Results

| Check | Observed result |
| --- | --- |
| Two finite fixture batches | Six captures each; first batch's immutable files unchanged after the second |
| Exit after durable reservation, before intent publication | Sequence 13 recovered as `abandoned/not_started`; next sequence 14 |
| Repeat recovery | Outcome totals, store identity and next sequence unchanged; diagnostic `recovered_capture` becomes null |
| Exit after response publication | Sequence 14 recovered as captured without a second fetch; next sequence 15 |
| Exit after durable verification hold | Both CLI status and run exit 2; collection remains blocked |
| Full verify, then another finite batch | Hold cleared; three new captures use sequences 15–17 |
| Full historical verification | 17 attempts: 16 captured, one abandoned, zero incomplete; 600 payload bytes verified; direct sequence lookup succeeds for 1–17 |
| Actual host reboot | Boot identity changed; verification hold still blocks status/run; all 83 existing capture/index file hashes unchanged |
| Resume after reboot | Full verify clears hold; three new captures finalize sequences 18–20; 20 attempts total (19 captured, one abandoned), 712 payload bytes, zero incomplete, next sequence 21 |

Fault injection uses the runtime adapter's existing checkpoint callback and `os._exit(77)`, without cleanup handlers. The [host helper](../../tests/helpers/host_checkpoint_process.py) does not override filesystem validation and is mounted read-only outside the image. The production CLI performs collection, recovery and full verification. Initial harness setup/exit-code/accounting assertions and guarded lookup during the verification hold were corrected before the results above; their failed attempts were retained separately. No collector implementation change was required.

This is synthetic fixture acceptance. It does not authorize live capture, establish provider retention/cadence, or certify sudden power-loss durability. Source policy, uploader confirmation, disk monitoring and external heartbeat remain gates in the [delivery plan](../delivery-plan.md).

## Reproduce the recovery checks

Build the named source revision and initialize a **new empty store** using the runbook. Never use an operational live store for fault injection. From the checkout containing the host helper, set the image and store paths, then define:

```bash
export CAPTURE_IMAGE=urbanpulse-capture:local
export CAPTURE_STORE=/srv/urbanpulse-capture/host-acceptance-v2
export CAPTURE_HELPER="$PWD/tests/helpers/host_checkpoint_process.py"

capture_cli() {
  docker run --rm --network none --read-only --cap-drop ALL \
    --security-opt no-new-privileges --memory 512m --pids-limit 128 \
    --mount "type=bind,src=$CAPTURE_STORE,dst=/data" \
    "$CAPTURE_IMAGE" "$@"
}
host_probe() {
  docker run --rm --network none --read-only --cap-drop ALL \
    --security-opt no-new-privileges --memory 512m --pids-limit 128 \
    --mount "type=bind,src=$CAPTURE_STORE,dst=/data" \
    --mount "type=bind,src=$CAPTURE_HELPER,dst=/host_checkpoint.py,readonly" \
    --entrypoint /app/.venv/bin/python "$CAPTURE_IMAGE" \
    /host_checkpoint.py "$@"
}
expect_exit() {
  expected="$1"; shift
  actual=0
  "$@" || actual=$?
  test "$actual" -eq "$expected"
}
```

Use `set -e` in the test shell and stop on any unexpected exit or count. The `hashes` action only inspects bytes under the store lock; `digest` additionally exercises guarded sequence lookup and must wait until full verify has cleared the hold. Keep output in a private evidence directory. After initialization, run:

```bash
capture_cli run --store /data --max-attempts 6 --max-seconds 120
host_probe digest > first-batch.json
capture_cli run --store /data --max-attempts 6 --max-seconds 120
host_probe digest > second-batch.json
expect_exit 77 host_probe capture reserve_synced
capture_cli status --store /data
capture_cli status --store /data
expect_exit 77 host_probe capture response
capture_cli status --store /data
expect_exit 77 host_probe verify verify_started
expect_exit 2 capture_cli status --store /data
expect_exit 2 capture_cli run --store /data --max-attempts 3 --max-seconds 120
capture_cli verify --store /data
capture_cli run --store /data --max-attempts 3 --max-seconds 120
capture_cli verify --store /data
host_probe hashes > before-reboot.json
expect_exit 77 host_probe verify verify_started
cat /proc/sys/kernel/random/boot_id > boot-before.txt
```

Compare every first-batch `hashes` entry with the corresponding second-batch entry; all must match. Check the sequence/accounting results against the table above. Schedule a collector maintenance window, stop capture work and reboot the rehearsal host normally. Before live deployment, separately verify the dedicated, always-on host requirements in ADR 0015. After reconnecting, restore the shell variables/functions and read back **before** clearing the hold:

```bash
cat /proc/sys/kernel/random/boot_id > boot-after.txt
# Boot IDs must differ; a reconnect alone does not prove reboot.
expect_exit 2 capture_cli status --store /data
expect_exit 2 capture_cli run --store /data --max-attempts 3 --max-seconds 120
host_probe hashes > after-reboot.json
cmp before-reboot.json after-reboot.json
capture_cli verify --store /data
capture_cli run --store /data --max-attempts 3 --max-seconds 120
capture_cli verify --store /data
capture_cli status --store /data
host_probe digest > final-sequences.json
```

Expect the original 17 immutable captures/index entries unchanged across reboot, then 20 attempts (19 captured, one abandoned), next sequence 21 and collection allowed. Preserve the store and its pinned image; do not remove verification markers manually. No automatic service or restart policy is installed by this procedure.
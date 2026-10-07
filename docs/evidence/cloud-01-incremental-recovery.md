# CLOUD-01 incremental capture recovery evidence

[ADR 0017](../adr/0017-incremental-capture-recovery.md) defines v2 recovery and sequence semantics. The [runbook](../runbooks/local-capture.md) covers fresh stores, verification and rollback; the [delivery plan](../delivery-plan.md) tracks remaining acceptance.

## Validation

- Ruff lint/format and mypy (76 source files) passed. The Windows unit run passed 684 tests, with 101 Linux-only cases skipped and 182 integration cases deselected; the collector filesystem/process suite runs separately below.
- The isolated Linux collector suite passed **131 tests** with no network, a read-only root, UID 10001 and test-only tmpfs admission. Production has no filesystem bypass.
- Tests terminate child processes around reservation write/replace/fsync, intent publication, payload/receipt/manifest publication, final accounting and reconstructed `not_started` publication. Repeated restart preserves outcome/sequence and contributes exactly once.
- Verification interruption, first-finding publication and success-report/removal boundaries are tested separately. A durable pre-scan hold survives abrupt interruption, failure-record write errors and unexpected exceptions. Fresh controlled cancellation can release only its own hold; a prior interrupted/failed scan requires full successful verification.
- Direct sequence lookup tests open only the padded index and referenced intent; clock-rollback tests cover all generated failure/abandonment outcomes and conservative Retry-After. Tests instrument file opens and enumeration: idle startup opens **no historical capture/session records and enumerates no directories**; pending recovery reads only the indexed capture. Historical corruption is deliberately invisible to fast status and detected by full verify.
- Control loss/corruption, stale valid control, duplicate sequence, overflow, Retry-After, partial initialization and read-only v1 inspection are covered. Both old and new journals reject the other's store version.
- The minimal runtime image reopened the persistent 1,000-capture store, verified all 8,192,000 payload bytes, then appended three fixture captures in another container. No provider key, live source or cloud resource was used.

## Startup measurement

Initial measurement at commit `fd757f228352991de6ff8851cbaac393f977a35b`, clean checkout: CPython 3.12.15, Docker Desktop's WSL2 Linux engine, ext4 named volume. The committed [benchmark helper](../../tests/helpers/benchmark_capture.py) generated real immutable captures with 8 KiB synthetic payloads and measured five lock/open/recover/close operations per archive size. Archive generation, file counting and Python process startup are excluded. These measurements predate the direct sequence index and pre-scan verification hold; they remain evidence for the named commit, not a new measurement of later heads. The revised implementation retains explicit bounded-read tests.

| Captures | Published payload bytes | Files including control/marker/lock | Startup samples (ms) | Median (ms) |
| --- | --- | --- | --- | --- |
| 10 | 81,920 | 43 | 2.464467, 1.529500, 1.211417, 1.072461, 0.814581 | 1.211417 |
| 1,000 | 8,192,000 | 4,003 | 0.986636, 0.678770, 0.625098, 0.689232, 0.602733 | 0.678770 |

These warm local measurements show no proportional archive scan; the file-access assertions establish the bounded read set independently of cache effects. They are not an Ubuntu-host latency target, an unbounded-history stress test or a disk/power-loss certification. The helper records code revision, dirty state, filesystem, runtime, all samples and the actual source-file hashes; line endings can change those hashes across checkouts.

Reproduce on a reviewed Linux checkout with Docker. Use a new disposable volume and retain the JSON output; do not point the benchmark at an operator store:

```bash
docker build --target test -f workers/capture/Dockerfile -t urbanpulse-capture:checkpoint-test .
export CAPTURE_BENCH_VOLUME="urbanpulse-capture-benchmark-$(date +%s)"
docker volume create --label urbanpulse.purpose=capture-checkpoint-benchmark "$CAPTURE_BENCH_VOLUME"
docker run --rm --network none --user 0 \
  --mount "type=volume,src=$CAPTURE_BENCH_VOLUME,dst=/data" \
  --entrypoint /bin/sh urbanpulse-capture:checkpoint-test \
  -c 'mkdir /data/store && chown 10001:10001 /data/store'
benchmark_dirty=()
if test -n "$(git status --porcelain)"; then benchmark_dirty=(--dirty); fi
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --memory 512m --pids-limit 128 \
  --mount "type=volume,src=$CAPTURE_BENCH_VOLUME,dst=/data" \
  --entrypoint /app/.venv/bin/python urbanpulse-capture:checkpoint-test \
  tests/helpers/benchmark_capture.py --store /data/store \
  --revision "$(git rev-parse HEAD)" "${benchmark_dirty[@]}" --counts 10 1000
docker volume rm "$CAPTURE_BENCH_VOLUME"
```

Actual Ubuntu fixture/reboot acceptance, source cadence/retention, uploader confirmations and external heartbeat remain separate. Normal startup cannot detect an old but internally valid checkpoint restored alone. A historical finding cannot silently permit restart when its diagnostic cannot be written: the pre-scan hold is already durable. Full verify compares retained history; backup/rollback must use a consistent stopped store.

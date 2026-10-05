# EVENT-01: Planning history copy cost

Progress: [delivery plan](../delivery-plan.md). Reproduction and measurement limits: [history benchmark](event-01-performance.md).

## Change

Every handler attempt still deep-copies its candidate projection and swaps it into place only after successful handling. Planning now retains accepted historical envelopes as immutable JSON strings. The history list, snapshot index, receipts, counters and latest model remain independently copied; copying a string cannot share mutable optional fields between candidates.

`history_events()` and `snapshot_states()` explicitly decode and validate all retained/indexed payloads into detached typed views on each call. Their cost scales with total payload size; call once outside loops and reuse the returned view. Profile construction decodes already validated retained envelopes into plain values, reconstructing typed historical records only for the removed-record view. It preserves original optional fields, source dates, statuses and event identities. Snapshot reuse compares the JSON state, preserving equivalent numeric spelling and the wire meaning of Python tuple extras after JSON serialization.

This is an internal in-memory representation change: persisted inputs, migrations, event contracts, retry behavior and HTTP responses stay unchanged. Request-local reconstruction still runs every prior transition clock. This does not introduce shared projections, a cache or incremental replay.

## Controlled comparison

Measured on 5 October 2026 on the same local Windows / Python 3.12.15 environment. Three samples after one warmup, at fixture second 360, with warm PostGIS membership caches and no concurrent test job. Both reports recorded `worktree_dirty: false`.

- Before: `5b81931b978ffa2ec914403f665d8ed0dcac4341` (approved PR #14 before rebase; identical tree to merged `ca014c74a5519858e667f1823aad604eae9cb163`).
- After: `bb6c787be7d7c9c388785d87972ba46589705bbe`.
- Workload: `planning-history-v1`; all six capture identities and load/snapshot/replay result fingerprints matched across versions.
- The two harness files have identical Git contents in both commits. Their raw file hashes differ only by CRLF/LF checkout conversion, verified against each report's hashes.

Milliseconds, median before -> after:

| Snapshots x records | Load | Single snapshot | Composed replay | Replay reduction |
| --- | ---: | ---: | ---: | ---: |
| 1 x 10 | 30.2 -> 29.9 | 17.8 -> 16.6 | 226.4 -> 203.0 | 10% |
| 10 x 10 | 50.3 -> 53.2 | 29.9 -> 24.6 | 448.5 -> 393.2 | 12% |
| 30 x 10 | 96.1 -> 95.7 | 88.5 -> 45.5 | 2129.6 -> 1147.8 | 46% |
| 1 x 100 | 48.2 -> 40.7 | 24.2 -> 20.6 | 308.0 -> 293.4 | 5% |
| 10 x 100 | 217.9 -> 194.5 | 117.6 -> 75.6 | 1542.3 -> 1146.6 | 26% |
| 30 x 100 | 582.0 -> 537.2 | 665.3 -> 199.0 | 12378.9 -> 5336.7 | 57% |

For the largest workload, replay samples ranged from 11554.6 to 12561.9 ms before, and 5122.2 to 5486.4 ms after. The separate instrumented replay reduced planning copy time from 7.46 to 0.70 seconds, with 689 planning copies in both versions. Total instrumented replay was 12.45 -> 5.47 seconds. Copy timings are attribution samples, not confidence intervals.

The improvement is strongest with longer history; input loading is unchanged and its timing differences reflect run variation. This is a bounded synthetic comparison, not a live latency target or proof of asymptotic complexity. Memory usage, concurrent users and cold caches were not measured. Full replay remains expensive at larger histories, so input validation/fingerprinting and repeated clock evaluation remain candidates for separately measured work.

## Reproduce and verify

Run the following on each comparison revision, with the same PostGIS service and no concurrent test jobs. Keep the output file under ignored `.local/`:

```powershell
uv run --locked python -m scripts.benchmark_city --output .local/benchmarks/planning-comparison.json
```

Compare case identities, result hashes, clean/dirty state and harness Git contents before comparing medians. A changed output hash is a correctness investigation, not a performance win. The baseline and final reports for this run are retained locally as `planning-before.json` and `planning-after.json` under `.local/benchmarks/`.

Verification passed:

- Ruff lint/format and mypy.
- 406 unit/API tests and 138 real PostGIS integration tests, including persisted replay and durable checkpoint equivalence.
- New regressions cover three consecutive failures after candidate mutation, successful retry without duplicate effects, nested optional fields, detached history/snapshot views, snapshot identity conflicts, numeric/tuple wire equivalence and removed-record provenance.
- All six benchmark cases retained identical output fingerprints for load, single snapshot and composed replay.

Repeated profile parsing and possible incremental summaries are tracked in [issue #16](https://github.com/maxtsec/urban-pulse-au/issues/16); measure attribution before changing retained derived state.

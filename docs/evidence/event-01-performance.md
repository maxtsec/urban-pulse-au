# EVENT-01: Growing planning history measurements

Progress: [delivery plan](../delivery-plan.md). Recovery design: [ADR 0008](../adr/0008-in-process-city-composition.md) and [ADR 0009](../adr/0009-durable-event-delivery.md).

## Reproduce

Start the local PostGIS service and run from the repository root:

```powershell
docker compose up -d --wait
uv run --locked python -m scripts.benchmark_city
```

The command reads `Settings.database_url`, creates a fresh randomly named `urbanpulse_bench_...` schema, migrates it, and imports only synthetic workloads there. It never activates a city import or migrates the application's schema. Its `finally` block removes only the schema created by that invocation, including when a measurement fails. A forced process kill can leave that temporary schema behind. The database role needs permission to create schemas.

Default cases combine 1, 10 and 30 planning snapshots with 10 and 100 records per snapshot. Each operation has one warmup and three measured repetitions. Run without concurrent tests or other benchmark jobs. A smaller boundary check is:

```powershell
uv run --locked python -m scripts.benchmark_city --histories 1 3 --records 2 --repeats 1 --output .local/benchmarks/city-small.json
```

The default report is `.local/benchmarks/city.json` (ignored by Git). It includes all timing samples, medians/ranges, result fingerprints, workload/capture identities, source hashes and runtime version. It excludes connection URLs, credentials and workstation paths. Bounds are 1–60 snapshots, 1–1000 records, and 1–20 repetitions; larger combinations can take substantially longer.

## Method

`planning-history-v1` replaces only the planning bundle in the retained integrated fixture. Development identities and positions stay stable; every complete snapshot has a distinct event/revision, increasing source date and rotating synthetic status. Receipts span seconds 0–300, with evaluation at second 360. This compresses historical snapshots into a fixture clock; it is not a claim about live DAM cadence or Southbank development volume. Transport and weather fixtures remain unchanged.

The harness verifies all snapshots were accepted and the final profile contains the expected history and records. It hashes results outside timing and fails if repetitions or the instrumented replay differ. It measures these boundaries separately:

- **Load:** a real `CityInputStore.load`, including SQL, decoding, contract validation and integrity hashing.
- **Single snapshot:** a fresh `CityService` using already loaded inputs, computing only the requested clock.
- **Composed replay:** a fresh `ComposedCityService` using already loaded inputs, rebuilding every transition clock and area event.
- **Copy profile:** a separate composed replay wrapping the handler's `deepcopy`, recording total and planning-only call counts/time. This instrumentation does not affect the ordinary latency samples.

A PostGIS adapter is shared within each case, so spatial caches are warm after warmup; services and projections are recreated each time. Increasing snapshot count also adds transition clocks. The benchmark therefore measures combined history/clock growth, not a fixed-clock algorithm experiment. These are sequential application measurements, excluding HTTP, input import, durable worker throughput, cold start, memory profiling and concurrent-user load. They are not production SLOs, and component medians should not be summed into a claimed HTTP latency.

## Results

Measured locally on 5 October 2026 with Windows and Python 3.12.15. Application baseline: `35a98097858922dc22f4acfe4fdb90668b27a2aa`; benchmark sources are introduced by this PR. Three repetitions per operation, with no concurrent test job. All durations below are milliseconds; cells show median [minimum–maximum].

| Snapshots × records | Transition clocks | Load | Single snapshot | Composed replay |
| --- | ---: | ---: | ---: | ---: |
| 1 × 10 | 17 | 30.4 [29.9–31.6] | 17.0 [16.3–17.7] | 240.1 [219.3–241.0] |
| 10 × 10 | 25 | 55.4 [55.0–55.5] | 31.8 [30.5–38.9] | 467.1 [466.6–520.8] |
| 30 × 10 | 45 | 110.4 [95.7–161.8] | 96.9 [85.2–99.2] | 1893.3 [1867.5–1914.8] |
| 1 × 100 | 17 | 43.1 [41.9–44.9] | 21.8 [21.6–22.3] | 300.5 [277.2–326.0] |
| 10 × 100 | 25 | 190.3 [188.7–201.1] | 105.6 [104.3–113.4] | 1404.3 [1368.3–1426.7] |
| 30 × 100 | 45 | 566.1 [546.0–587.2] | 626.5 [617.9–638.1] | 11401.6 [11397.5–11822.3] |

In the separate 30 × 100 profile, 1482 handler copies took 7.21 seconds in a 11.91-second replay. Planning accounted for 689 copies and 7.14 seconds (60% of that instrumented replay). These are attribution samples, not confidence intervals or proof of asymptotic complexity.

Harness SHA-256:

- `benchmark_city.py`: `62dee5ac77fc9ae6f63b7f2a1e0e535a15498e1b1fd8a0de29e8e56171f14f7d`
- `benchmark_workload.py`: `a5c5fea1a9a9c48d7d8a5222439a9ffcbf5af74d527a2bfb600d097b82ad4dbc`

## Interpretation and next change

The larger history spends substantial time rebuilding earlier clocks and copying retained planning projections. A first performance PR should reduce historical-object copying while preserving atomic candidate-state rollback, receipts and duplicate/conflict outcomes. Compare it with this baseline and include failure-injection tests proving the original projection is untouched when a handler fails.

Incremental reconstruction and input caching are separate candidates. Any cache must preserve import/version invalidation, clock/scenario isolation and explicit database-unavailability behavior. Replacing reconstruction with shared mutable state would require a separate architectural decision. This measurement change adds no production cache, persistent model or delivery behavior.

## Verification

- Workload tests cover bounds, deterministic identity, source/receipt times, accepted revisions and the 1000-record contract limit.
- Instrumentation tests check unchanged replay results and restoration of the original handler function, including failure.
- Real PostGIS tests cover isolated import/replay without active-import selection and schema cleanup on success or failure.
- Local checks: Ruff lint/format, mypy, 397 unit/API tests and 2 benchmark PostGIS tests passed.
- Normal tests assert behavior, not timing thresholds; timing evidence is machine-dependent.

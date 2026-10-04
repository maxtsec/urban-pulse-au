# Testing and quality strategy

This strategy maps the integrated city brief to evidence across Transport, Weather & Hazards, Planning & Infrastructure and Location Intelligence. Feature timing and implementation status are maintained in the [delivery plan](delivery-plan.md). See [development setup](development.md) for prerequisites and [recorded local evidence](evidence/phase-0-local.md) for observed results.

## Checks available now

| Check                    | Command from repository root                                                                  | What it establishes                                                                                  |
| ------------------------ | --------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| Python/frontend baseline | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check.ps1`                       | Ruff lint/format, mypy for API/worker/contracts/domain, fixture and contract/domain pytest tests, ESLint, Prettier, TypeScript and Vite build |
| PostGIS/Redis smoke      | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/services-smoke.ps1`              | Container health, executable PostGIS query and Redis ping                                            |
| HTTP fixture smoke       | `uv run --locked python scripts/smoke.py`                                                     | API liveness, Vite HTML and proxy response; temporary processes are stopped                          |
| Worker capture           | `uv run --locked python -m workers.ingestion.main --once`                                     | Synthetic bytes written to a content-addressed local path                                            |
| Dagster/Parquet smoke    | Materialize `fixture_parquet`; see [demo steps](demos/phase-0.md#independent-data-tool-smoke) | Local asset execution and Parquet roundtrip                                                          |
| Offline dbt parse        | See [development guide](development.md#checks-and-analytics-smoke)                            | Project/config parsing; no warehouse execution                                                       |

Baseline tests assert fixture labeling, null/negative delay preservation and repeated file-capture identity. [Event tests](../tests/unit/test_events.py) exercise serialized compatibility, invalid input, documentation/fixture agreement, UTC identity, duplicate/older revisions and conflicts. [Area tests](../tests/unit/test_area_status.py) exercise separate condition/coverage, warning expiry, explicit resolution and failure without false recovery using a controlled clock. These pure tests do not establish persistent deduplication, spatial/source freshness correctness, database transactions or publication recovery. Frontend build/lint is not a component or browser test. HTTP smoke does not execute React in a browser.

The [current CI workflow](../.github/workflows/check.yml) runs dependency restore, Python checks and frontend checks on Linux. It does not run Docker integration, HTTP smoke, Dagster materialization, dbt execution or GCP tests. A workflow file is not evidence of a passing hosted run; record the run URL after observing completion.

## Coverage to add with features

| Boundary                  | Important cases                                                                                                                                                                 | Required test/evidence                                                                                   |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| Transport domain/metrics  | Missing vs zero delay, negative values, predicted/observed eligibility, sampling, DST and after-midnight service times                                                          | Deterministic unit tests with approved examples                                                          |
| Weather & Hazards         | Warning issue/update/cancellation/expiry, official severity, timezone and malformed geometry                                                                                    | Deterministic clock-based tests and adapter contracts                                                    |
| Planning & Infrastructure | Snapshot identity, changed/removed records, source statuses, slow cadence and unsupported geography                                                                             | Fixture contracts and real spatial integration                                                           |
| Location Intelligence     | Cross-domain spatial/time overlap, missing/stale sources, status reasons and no false recovery                                                                                  | Approved rule examples, unit tests and PostGIS boundary cases                                            |
| Event delivery            | Commit/publish crash, duplicate delivery, out-of-order revisions, bounded retry, dead-letter and replay                                                                         | Phase 2 shared-envelope/handler tests; phase 3 real delivery/database boundary and acknowledgement tests |
| Provider/parser           | Valid/malformed input, optional fields, size bounds, timeout/rate limit and schema changes                                                                                      | Contract tests using synthetic or redistributable recorded fixtures                                      |
| Operational store         | Migrations, unique identity, spatial bounds, transactions and late-event precedence                                                                                             | Real PostGIS integration tests                                                                           |
| Capture/replay            | Identical and overlapping captures; crash after raw write or persistence                                                                                                        | Manifest reconciliation and retry tests with row-count/content assertions                                |
| Cache                     | Miss/expiry, invalidation races, late old-version fills, outage and fallback limits                                                                                             | Real Redis integration and controlled dependency-failure tests                                           |
| Warehouse                 | Bounded load, IAM, dbt SQL/tests and isolated datasets                                                                                                                          | Real BigQuery integration with scoped credentials                                                        |
| Analytical pipeline       | Partition/backfill boundaries, incremental/full equivalence and failed publication                                                                                              | Fixed reference inputs, SQL result comparison and cross-store failure injection                          |
| UI                        | Successive vehicle positions, stale markers, city map/layer/area selection, panel/history/filter behavior, loading/empty/error/stale/insufficient-data states and accessibility | Component tests and a fixture-driven browser flow                                                        |
| End to end                | Three-domain capture through area processing to visible map/panel; historical publication when implemented                                                                      | Deterministic full fixture path after these stages exist                                                 |
| Performance               | Warm/cold cache, stated concurrency and simultaneous backfill                                                                                                                   | Reproducible benchmark with data size, host, date and raw results                                        |
| AI tools                  | Defects and legitimate cases, semantic SQL equivalence, classification and rejection                                                                                            | Held-out evaluations against an agreed baseline                                                          |

## Capture and event acceptance

For CLOUD-01, verify a real permitted object/manifest roundtrip, idempotent retries, worker restart, secret/identity scope and retention configuration. Record missing capture intervals and source age while the API/warehouse are offline. This verifies the early collector independently of full application deployment.

For CONTRACT-01 and phase 2, test serialization and version compatibility of the shared envelope, stable event identity, duplicate/older input handling, failure outcomes and area recomputation from persisted state. Run the same handler contract suite against the phase 3 durable adapter, then add crash-after-commit/before-ack and retry/dead-letter/replay tests.

Measure the proposed area update and warning-expiry targets in [brief section 12](../project_brief.md#12-observability-and-operating-targets) after A-04 accepts their thresholds. Separate source delay, projection lag and browser delivery; include expiry with no new incoming event.

## Execution boundaries

Ordinary pull-request tests use fixtures without provider/cloud credentials. Service integration uses disposable test data and explicit database ownership. Do not run destructive test setup against a developer's retained database.

Real cloud integration belongs in a trusted job using short-lived credentials, isolated datasets, expiration, bounded query cost and cleanup even after failure. Untrusted PRs must not receive deployment credentials. Live-provider probes remain optional and separate from ordinary checks. Schedule these jobs with their corresponding service/cloud boundaries in the delivery plan.

Cross-domain fixtures must include warning expiry while transport remains disrupted, a failed source that must not improve status, planning data outside its supported municipality, and duplicate/older updates. Numeric score tests wait for an approved metric definition; no synthetic expected score can define the product by accident.

Fixtures should identify provenance, redistribution permission when applicable, schema version and expected behavior. Keep synthetic and live records clearly labeled. Pin reference inputs for result comparisons so changing source data cannot create misleading test outcomes.

## Acceptance and review gates

For each feature, connect acceptance cases to test names and applicable integration evidence. Prefer behavioral assertions over implementation mirrors. Add regression coverage for reproducible bugs; exercise meaningful failure paths where the feature introduces them.

Before review, run affected checks and report commands, outcomes, skipped checks and unresolved limitations. If a feature requires warehouse behavior, a successful local parse is insufficient to call it verified. Code can be reviewed with an explicit blocker while its required integration acceptance remains open.

Before closing a phase, demonstrate its exit criteria, create its Git tag, and attach release notes, demo/evidence, a passing CI run and relevant measurements. No arbitrary coverage percentage replaces those behavioral checks. Revisit coverage and performance targets with evidence as the implementation grows.

# Local DuckDB/dbt analytics evidence

Date: 2026-10-12. Implements [ADR 0024](../adr/0024-local-duckdb-analytics.md); reproduction commands are in the [runbook](../runbooks/local-tram-analytics.md).

## Executed boundary

Windows, CPython 3.12.15, DuckDB 1.5.6, dbt-duckdb 1.11.0 and dbt-core 1.12.5, restored from `uv.lock` with the analytics dependency group. Real local dbt execution: **7 models and 14 data tests passed**. No cloud or provider calls were part of the pipeline; automatic DuckDB extension downloads and dbt telemetry are disabled.

The 24-hour synthetic fixture produces 192 area rows and 288 feed-window rows. Tests distinguish a valid empty feed (zero) from missing/failed captures (null), deduplicate resends, retain later-window receipt age, isolate conflicting observations, preserve missing/invalid source values, refuse input hash changes and concurrent builds, and remove accepted-output markers/CSVs when dbt fails. Rebuilding identical input produces identical ordered CSV bytes.

## Repository checks

- Ruff lint and formatting: passed. Strict mypy: 93 source files passed.
- New offline analytics tests: 11 passed, including actual dbt builds and conflict isolation with and without another valid vehicle.
- Full Windows suite: 974 passed, 183 skipped, 190 deselected; two pre-existing heartbeat deadline cases failed their call-count assertion with a 50 ms budget. Both passed when rerun in isolation (2 passed). The collector implementation and these tests are unchanged. The full-suite run therefore is not reported as all-green.
- Local documentation links in changed reading paths: 339 resolved; whitespace check passed.
- PostGIS/container/browser acceptance was not repeated for this local analytical change; CI retains those checks. Linux-specific tests remain platform-skipped on Windows.

## Retained real probe

The private SRC-02 sample from 7 October was processed without fetching new data: 11 captures (five positions, three trip updates, three alerts), 577 source position rows. One vehicle/observation group had conflicting coordinates. All original rows remain in staging; the group is excluded from metrics and counted as a conflict. There are 383 eligible deduplicated observations across the selected two receipt windows.

Both area and collection marts built successfully. A second complete build produced byte-identical CSVs. Every retained source file hash was checked before and after preparation/build and remained unchanged. Private payloads, row-level results and generated files are not committed.

## Limits of this evidence

- The real sample spans minutes, not a full day. A one-day real capture audit/export and full-day runtime/memory measurements remain outstanding.
- The fixture covers a day of windows, not a day's realistic volume.
- v3 reader tests use immutable synthetic store contents, including an outstanding pending capture and an existing collector lock file; the home collector was not started or changed.
- This is position-only local analysis. Stop-update/alert normalization, full-field coverage, Schedule archive rollout, upload, raw expiry, BigQuery and PostGIS publication are outside this verification.
- No map/backend integration or cloud deployment is asserted. The public sample remains independent.

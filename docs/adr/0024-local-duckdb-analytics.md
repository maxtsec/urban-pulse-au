# ADR 0024: Local Tram analytics with DuckDB and dbt

Status: Accepted by the project architect, 2026-10-12 (local engine, metrics and conflict isolation).

## Decision

Use Polars to prepare private analytical Parquet, then a separate `pipelines/dbt_local` project with `dbt-duckdb`. Run explicitly on a local computer, without cloud credentials, services, scheduling or provider requests. Keep the BigQuery project as a future target; SQL portability is not yet established.

Inputs may be a synthetic fixture, an existing SRC-02 probe directory or a read-only v3 capture store. Finalized sequence indices bound the store snapshot. Do not acquire its writer lock, write downstream progress, enable expiry, restart collection or change its format. Prepared inputs and build outputs live in a separate ignored directory.

This **position-only analytical projection** is independent of full `tram-normalized-v1`. It does not claim lossless positions/stop updates/alerts coverage, a schema freeze, a completed one-day field audit, upload confirmation or expiry eligibility. The cloud Schedule archive prerequisite remains for the full Phase 1a export; this local spatial exploration needs only pinned area boundaries and is explicitly exempt. No trip-to-shape or timetable inference is performed.

## Metrics

All windows are half-open UTC receipt intervals `[start, start + 15 minutes)`. A capture without a receipt uses its requested time for failure accounting. UTC days avoid ambiguous daylight-saving times; a local service-day analysis needs separately explicit date boundaries.

| Output | Rule |
| --- | --- |
| Observed vehicle count | Distinct non-empty `vehicle_id` whose reported point is covered by the Southbank or CBD CLUE boundary; includes boundary points, no buffer. It is neither an in-service count nor a delay/congestion measure. |
| Median position age | `received_at - observed_at`, in seconds. Missing or reversed times remain quality issues and have no age value. The feed header never substitutes for a missing entity timestamp. |
| Resends | Earliest receipt per store, vehicle and observation time **within each receipt window**. Across windows the observation can appear again with its later receipt age. Missing identity/time cannot establish equality and remains separate source rows. |
| Conflicts | Same store/vehicle/observation time with different coordinates or trip-instance fields: retain all staging rows, isolate the group from both count and age, and expose affected-area `conflict_count`. Detection spans the whole prepared interval, so a changed interval may reveal a later correction. No arbitrary winning coordinate. |
| Missing data | No successful position capture means a null vehicle count. A valid empty capture permits zero. If no identifiable vehicles remain and conflicts/unknown location/missing identity could hide membership, return null. A nonzero count with quality issues is a known subset, not proof of completeness. |
| Collection coverage | Per feed: successful/failed captures and maximum silence **within the window**, including window edges. No successful capture yields 900 seconds. This is not the complete multi-window outage length or an operational alert threshold. |

`conflict_count` counts groups with a received record located inside that area (or unknown location). `unknown_location_count` and `missing_vehicle_id_count` are feed-wide diagnostics repeated on each area's row; do not add them across areas. Area `quality_issue_count` counts located, non-conflicting observations with an issue. Inspect staging for source-row detail.

Empty periods remain explicit in both marts. Feed timestamps preserve UTC microseconds. Spatial membership uses the same point-including-boundary rule as the pilot (`covers`), implemented locally with Shapely; both boundary hashes accompany results.

## Integrity and publication

Source-row keys hash the table, store/capture identity and source ordinal, independently of transformer version. Input manifests pin table hashes and provenance; retained probes verify their original hashes, and v3 input reuses the bounded field audit. Source files remain private.

A build verifies Parquet hashes, runs dbt models and data tests, then exports ordered CSVs plus `build-success.json`. Failed builds publish neither success marker nor CSVs; intermediate DuckDB tables are not an accepted publication. A per-output-directory exclusive lock prevents concurrent builds. Complete rebuilds are the initial idempotency strategy, not an incremental/backfill protocol.

Limits: at most 26 hours, 10,000 captures, 2 GiB source payload and 300,000 position rows per preparation; each Parquet input at most 512 MiB. These are exploratory bounds, not demonstrated full-day capacity. DuckDB runs one thread with a 512 MiB memory setting (not a whole-process hard cap), no automatic extension downloads, and a five-minute build timeout. Dependencies must be installed before offline execution.

## Consequences

This delivers a reproducible local data-engineering slice while cloud resources and collection remain stopped. The full historical schema, unknown-field audit, late-data policy, service-date partitions, warehouse publication and frontend integration remain separate work. See the [runbook](../runbooks/local-tram-analytics.md) and [evidence](../evidence/local-tram-analytics.md).

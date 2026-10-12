# Local Tram analytics

Run from the repository root with Python 3.12 and uv. No database server, Docker, provider key or Google login is needed. Outputs are private under `.local`; do not publish collected feed data. [Metric definitions](../adr/0024-local-duckdb-analytics.md) distinguish observed vehicles, source age and collection gaps.

## Install and try a full-day fixture

```powershell
uv sync --locked --group analytics
uv run --locked --group analytics python -m scripts.local_tram fixture --output .local/analytics/example --start 2026-10-08T00:00:00Z --end 2026-10-09T00:00:00Z
uv run --locked --group analytics python -m scripts.local_tram build --input .local/analytics/example
```

The fixture has a few known captures and deliberately empty periods across 24 hours. It demonstrates coverage, not a day of realistic traffic. Each preparation requires a **new output directory**; rebuilding the same prepared inputs is supported.

Open `mart_area_tram_15m.csv` for CBD/Southbank or `mart_capture_15m.csv` for all three feeds. A null count means unavailable; it is not zero. Confirm `build-success.json` exists for the latest build before using exports. `manifest.json` labels input kind and pins all Parquet hashes; `target/run_results.json` contains individual dbt results.

## Existing private captures

For a retained bounded SRC-02 probe, point at the directory containing its original `report.json` and protobuf files. Set the interval to cover its receipts, aligned to UTC quarter hours:

```powershell
uv run --locked --group analytics python -m scripts.local_tram probe --input .local/my-retained-probe --output .local/analytics/probe --start 2026-10-07T03:30:00Z --end 2026-10-07T04:00:00Z
uv run --locked --group analytics python -m scripts.local_tram build --input .local/analytics/probe
```

For a local copy of the encrypted host's v3 raw store:

```powershell
uv run --locked --group analytics python -m scripts.local_tram store --input .local/private-raw-copy --output .local/analytics/day --start 2026-10-08T00:00:00Z --end 2026-10-09T00:00:00Z
uv run --locked --group analytics python -m scripts.local_tram build --input .local/analytics/day
```

Use a fully copied, immutable snapshot or finalized captures with expiry disabled; do not export from a concurrently modified copy. `--first` and `--last` optionally bound capture sequences. By default the finalized high-water mark excludes the pending capture. The reader validates source manifests/receipts/hashes, refuses expiry/policy activity and mixed live/fixture selections, and never writes the store or takes the collector lock. The output must be separate from the source directory. A running collector is not required.

The commands do not fetch anything, upload anything, create cloud resources, unlock the home volume or resume collection. Raw inputs and generated databases remain ignored. Do not move them into tracked fixture directories.

## Query the database

Save this as a local Python file, adjust `path`, then run with `uv run --group analytics python <file>`. Keeping it in a file avoids PowerShell quoting of inline SQL.

```python
import duckdb

path = ".local/analytics/example/local_tram.duckdb"
with duckdb.connect(path, read_only=True) as db:
    db.execute("SET TimeZone = 'UTC'")
    print(
        db.sql("""
            select window_start, area_id, observed_vehicle_count,
                   median_position_age_seconds, conflict_count, coverage
            from analytics.mart_area_tram_15m
            order by window_start, area_id
            limit 12
        """)
    )
    print(
        db.sql("""
            select window_start, feed, successful_capture_count,
                   failed_capture_count, max_success_gap_seconds
            from analytics.mart_capture_15m
            where successful_capture_count = 0
            order by window_start, feed
            limit 12
        """)
    )
```

Detailed positions live in `analytics.stg_positions`; deduplicated eligible observations in `analytics.int_observations`; quarantined identities in `analytics.int_observation_conflicts`. Use a bound SQL parameter for a private vehicle ID and filter `received_at` to inspect a particular hour. Trip updates and alerts currently supply capture coverage only: no stop-level transformation or alert interpretation is claimed.

## Rebuild and diagnose

Run `build` again against the same prepared directory. Rows and ordered CSV bytes should match. Conflicting observations remain visible in staging but cannot contribute to counts or medians; only-conflict windows return N/A. Time/identity/location issues remain explicit. A successful capture is a decodable full-dataset feed, not proof that every row is analytically usable.

Hash failures, invalid capture relationships and failed dbt tests stop publication. Inspect dbt logs and `target/run_results.json`; never treat leftover intermediate DuckDB tables as approved output. Export files are cleared before a rebuild and after any caught failure. A hard process kill can leave `build.lock`; confirm no build process still owns the directory, remove only that lock, then rerun the complete build. Do not edit source captures or hashes to bypass validation.

For dbt lineage documentation, after a successful build set `URBANPULSE_PARQUET_DIR` and `URBANPULSE_DUCKDB_PATH` to that directory/database and run the local project explicitly. Keep generated documentation private: manifests can contain local paths and source lineage.

## Tests

```powershell
uv run --locked --group analytics pytest tests/test_local_tram.py -q
uv run --locked --group analytics mypy
uv run --locked --group analytics ruff check .
uv run --locked --group analytics ruff format --check .
```

The tests execute real DuckDB/dbt builds, not mocked SQL. The CI installs the optional analytics group. This slice does not replace the [full normalized-history contract](../architecture/normalized-tram-contract.md) or authorize expiry.

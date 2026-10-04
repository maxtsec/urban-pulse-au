# Phase 0 demonstration

Purpose: show that the local toolchain, fixture API/UI connection and independent data-tool smoke paths work. Audience: developers or reviewers evaluating the starting point. Suggested presentation length: 5-10 minutes; this is a presentation plan, not measured setup time.

See the [delivery plan](../delivery-plan.md#milestones-and-exit-evidence) for phase completion and the [implementation baseline](../delivery-plan.md#implementation-baseline) for the data paths used here.

## Preparation

Follow the [development guide](../development.md). Use Windows PowerShell from the repository root with installed dependencies and Docker Desktop running. Ports 8000, 5173, 5432 and 6379 must be available to this project; port 3000 is needed only for the optional Dagster UI.

Record `git rev-parse HEAD` and `git status --short` before collecting evidence. Use a clean checkout/commit for a release recording, and identify any working-tree changes for a development walkthrough. Label all displayed data as synthetic.

## 1. Show the starting point

Open the README. Explain the product question, the three input domains and Location Intelligence. Show the [planned city scenario](city-mvp.md), then explain that the next transport slice establishes the area/map foundation. State that the UI currently reads fixture JSON directly and that local worker/Dagster commands are separate demonstrations.

## 2. Demonstrate automated checks

Run before starting foreground API/UI processes:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/services-smoke.ps1
uv run --locked python scripts/smoke.py
```

Expected: two pytest tests pass, frontend builds, PostGIS returns a version, Redis returns `PONG`, and the HTTP smoke prints `PASS`. Show the known test-client deprecation warning if present; do not conceal failed/skipped checks. The HTTP check stops its servers on completion.

## 3. Show the UI and API

Start API and Vite in separate terminals using the [development guide](../development.md#services-and-application). Open `http://127.0.0.1:5173` and then `http://127.0.0.1:8000/docs`.

Expected UI: a synthetic-data label and three rows containing 120 seconds, Unknown and -30 seconds. Explain that unknown delay is not zero and an early value may be negative.

With the API running:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health/live
Invoke-RestMethod http://127.0.0.1:8000/health/ready
Invoke-RestMethod http://127.0.0.1:8000/api/v1/fixture
```

Expected: liveness is OK; readiness reports PostGIS and Redis OK when services are available; the fixture response includes `mode: fixture`. These checks prove local connectivity, not live-feed freshness.

## Independent data-tool smoke

Optional extension to the presentation, using a third terminal:

```powershell
uv run --locked python -m workers.ingestion.main --once
uv run --locked python -m workers.ingestion.main --once
```

Expected: identical `capture_id` values and one content-addressed file for that payload under `.local/raw/`. Existing other files can remain. This demonstrates stable file identity; it does not prove database observation deduplication or crash recovery.

Materialize the Dagster asset and check the generated Parquet directly:

```powershell
@'
from dagster import materialize
from pipelines.dagster.definitions import fixture_parquet
import polars as pl
result = materialize([fixture_parquet])
assert result.success
frame = pl.read_parquet(".local/curated/fixture.parquet")
assert frame.height == 3
assert frame["delay_seconds"].null_count() == 1
print("Parquet smoke passed: 3 rows, 1 unknown delay")
'@ | uv run --locked python -
```

Expected: successful materialization, three rows and one null delay. The asset reads the original fixture independently of the worker output.

For optional dbt parsing, use the dedicated-terminal instructions in the [development guide](../development.md#checks-and-analytics-smoke). Explain why an offline parse does not establish warehouse correctness.

## Capture evidence and finish

Use the [evidence record](../evidence/phase-0-local.md) as the evidence index. Save the source revision, environment, commands/results, dates, limitations and any measured durations. Screenshots/recordings should include the synthetic label and identify their release or commit.

Close foreground servers with Ctrl+C. `docker compose down` stops the dependency containers while retaining the database volume. Demo reruns can reuse fixture files; do not clear unrelated captures or database volumes.

If live presentation setup fails, show a previously recorded walkthrough tied to a verified revision, when one exists, and disclose the current failure. Until a recording is available, use the written evidence and explain its limits.

## Phase completion

Use the exit criteria in the [delivery plan](../delivery-plan.md#milestones-and-exit-evidence). Tag the completed phase and attach its demonstration, validation results and release notes to that revision.

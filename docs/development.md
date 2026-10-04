# Development guide

Run commands from the repository root unless stated otherwise. See the [implementation baseline](delivery-plan.md#implementation-baseline) for available behavior and [milestones](delivery-plan.md#milestones-and-exit-evidence) for progress.

## Prerequisites and installation

The local scripts target Windows PowerShell. Install Git, uv, Node.js 24 LTS with npm, and Docker Desktop using the WSL 2 backend. Open VS Code at the repository root and install its recommended extensions. Terraform and Google Cloud CLI are needed for future cloud work, not the offline fixture demo.

Python's exact version is in [`.python-version`](../.python-version); Node's tested version is in [`.node-version`](../.node-version). Python dependencies are locked in `uv.lock`; frontend dependencies are locked in `apps/web/package-lock.json`.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1
```

This restores locked dependencies and creates `.env` from `.env.example` only if `.env` is missing. It does not install system tools or start Docker. Reopen terminals after tool installation so PATH changes take effect. A first WSL/virtualization setup may require Windows restart.

CI uses Linux with explicit uv/npm commands; these PowerShell scripts have not been validated as a cross-platform installer.

## Services and application

Start Docker Desktop, then:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/services-smoke.ps1
```

Expected: healthy PostgreSQL/PostGIS and Redis containers, a PostGIS version result and `PONG`. Ports 5432 and 6379 bind to loopback. Compose uses local development credentials; it is not a deployment configuration.

Start the API and UI in separate terminals:

```powershell
uv run --locked uvicorn apps.api.main:app --reload --host 127.0.0.1 --port 8000
```

```powershell
npm.cmd --prefix apps/web run dev
```

| Address                        | Current behavior                                           |
| ------------------------------ | ---------------------------------------------------------- |
| `http://127.0.0.1:5173`        | Synthetic fixture table through the Vite proxy             |
| `http://127.0.0.1:8000/docs`   | Generated API documentation                                |
| `/health/live` on port 8000    | Process liveness with a fixture label                      |
| `/health/ready` on port 8000   | Checks both PostGIS and Redis; returns 503 if either fails |
| `/api/v1/fixture` on port 8000 | Reads the static JSON fixture directly                     |

Readiness is separate from the fixture response. The fixture endpoint works without databases. The target cache-outage behavior is defined in the [brief](../project_brief.md#8-redis-and-graceful-degradation).

VS Code tasks: **Dev: services**, **Dev: API + Web**, **Dev: Dagster**, and **Check**. F5 runs the API debugger. The interpreter is `.venv/Scripts/python.exe`. Markdown preview is **Ctrl+Shift+V**; side-by-side preview is **Ctrl+K V**.

## Configuration boundaries

| Setting                                                         | Current consumer and behavior                                                         |
| --------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| `DATABASE_URL`, `REDIS_URL`                                     | API settings; read environment variables and root `.env`                              |
| `RAW_STORAGE_PATH`                                              | Worker process environment; defaults to `.local/raw`; the worker does not load `.env` |
| `VITE_API_PROXY`                                                | Vite process environment; defaults to `http://127.0.0.1:8000`                         |
| `GOOGLE_CLOUD_PROJECT`, `BIGQUERY_DATASET`, `BIGQUERY_LOCATION` | dbt process environment; `.env` is not loaded by dbt                                  |
| `URBANPULSE_MODE`                                               | Reserved placeholder in `.env.example`; changing it does not enable live ingestion    |

The sample BigQuery location is a configuration example, not an approved cloud placement decision. Keep credentials outside the repository and frontend bundle.

## Checks and analytics smoke

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check.ps1
uv run --locked python scripts/smoke.py
```

Stop host API/UI servers before the second command. It uses ports 8000 and 5173, verifies HTTP connectivity and stops its temporary servers. Logs are under `.local/smoke/`. It does not exercise a real browser or the database path. See [testing strategy](testing-strategy.md) for scope.

```powershell
uv run --locked python -m workers.ingestion.main --once
uv run --locked dagster dev -m pipelines.dagster.definitions --host 127.0.0.1
```

The worker writes a content-addressed copy of the synthetic fixture to `.local/raw/`. Dagster's UI is at `http://127.0.0.1:3000`; materialize `fixture_parquet` to write `.local/curated/fixture.parquet`. The asset independently reads the fixture; it does not consume worker output. Persistent Dagster metadata is not configured.

To parse dbt without cloud access, use a dedicated terminal with an explicitly non-live project identifier:

```powershell
$env:GOOGLE_CLOUD_PROJECT = 'urbanpulse-offline-placeholder'
uv run --locked dbt parse --project-dir pipelines/dbt --profiles-dir pipelines/dbt --no-partial-parse
```

Parsing verifies local project structure and configuration, not BigQuery execution or permissions. Do not use the placeholder for a cloud build.

## Developing city features

Read the [brief](../project_brief.md), [domain boundaries](architecture/overview.md) and [decision queue](delivery-plan.md#decisions-needed-before-dependent-work) before adding a slice. Implement a narrow end-to-end behavior with deterministic tests, preserve each source's temporal/spatial meaning and keep adapters separate from domain rules.

The existing fixture endpoint is a smoke interface, not the future area API contract. Adding another domain needs its own fixture schema, validation and coverage semantics. Do not fill missing weather/planning values with zeros or treat development activity as an automatic health benefit.

The [city MVP scenario](demos/city-mvp.md) describes intended acceptance behavior. Move shared configuration out of API entry points when implementing the first related structural change.

## Cloud work

CLOUD-01 runs in parallel, targeting phases 1-2, to establish minimal continuous capture: approve A-06, source retention and the capture contract first, then provision the bucket/worker from reviewed resource definitions. Track its retained date range and gaps. Full application deployment is CLOUD-02 in phase 4; BigQuery/dbt execution belongs to phase 5. For warehouse work, approve dataset locations, scoped access and query limits. In a separate terminal after resource setup:

```powershell
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud auth application-default login
$env:GOOGLE_CLOUD_PROJECT = 'YOUR_PROJECT_ID'
$env:BIGQUERY_DATASET = 'YOUR_ISOLATED_DATASET'
$env:BIGQUERY_LOCATION = 'YOUR_APPROVED_LOCATION'
uv run --locked dbt debug --project-dir pipelines/dbt --profiles-dir pipelines/dbt
```

A later `dbt build` with the same project/profile arguments creates the synthetic view and runs warehouse tests. It requires real permissions and may incur charges.

## Clean-checkout verification

Use the [isolated rehearsal](demos/clean-checkout.md) to restore a new checkout and test fresh PostGIS/Redis services alongside an existing development environment. The [BASE-01 record](evidence/base-01-clean-checkout.md) gives the tested revision, timings and cache conditions.

## Stop, restart and troubleshoot

Stop foreground API, Vite and Dagster processes with Ctrl+C in their terminals. `docker compose down` stops services while retaining the named PostgreSQL volume. Avoid deleting volumes to resolve routine startup problems.

| Symptom                             | Check or next step                                                                                      |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------- |
| Tool not found                      | Reopen the terminal; confirm system installation and PATH                                               |
| Docker pipe/backend unavailable     | Open Docker Desktop and wait for its engine; verify WSL and restart Windows if required by installation |
| Port already in use                 | Stop the earlier project server in its terminal; use one host/container application mode at a time      |
| Fixture request fails in UI         | Check the API on port 8000, Vite terminal output and proxy target                                       |
| Readiness returns 503               | Run `docker compose ps`, service smoke checks and inspect service logs                                  |
| Python environment mismatch         | Select the root `.venv` interpreter and rerun `uv sync --locked`                                        |
| dbt cannot find project/credentials | Use shell environment variables for dbt and distinguish offline parsing from cloud execution            |

The optional development container command is `docker compose --profile app up -d --build --wait`. Its application image builds are not yet verified. Stop host servers first. The current profile has dependency healthchecks but no API/UI readiness healthchecks; use HTTP checks after startup rather than treating `--wait` as an application acceptance test.

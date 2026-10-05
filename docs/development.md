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
| `http://127.0.0.1:5173`        | Southbank fixture map and area panel through the Vite proxy             |
| `http://127.0.0.1:8000/docs`   | Generated API documentation                                |
| `/health/live` on port 8000    | Process liveness with a fixture label                      |
| `/health/ready` on port 8000   | Checks both PostGIS and Redis; returns 503 if either fails |
| `/api/v1/fixture` on port 8000 | Reads the static JSON fixture directly                     |

Readiness is separate from the fixture response. The original `/api/v1/fixture` works without databases; `/api/v1/areas/au-vic-melbourne-clue-southbank` requires PostGIS, migrated city tables and an explicitly imported fixture scope. Redis is not used by city queries. The target cache-outage behavior is defined in the [brief](../project_brief.md#8-redis-and-graceful-degradation).

VS Code tasks: **Dev: services**, **Dev: API + Web**, **Dev: Dagster**, and **Check**. F5 runs the API debugger. The interpreter is `.venv/Scripts/python.exe`. Markdown preview is **Ctrl+Shift+V**; side-by-side preview is **Ctrl+K V**.

## City input setup and recovery

After starting PostGIS, run:

```powershell
uv run --locked python -m urbanpulse.adapters.city_store migrate
uv run --locked python -m workers.ingestion.main --city-fixture
```

The import normalizes the retained synthetic bundle once, atomically saves owned domain history in PostgreSQL, and selects that complete import in `city04_active_imports` in the same transaction. Repeating the import verifies the same content and selects the same scope. A failed import preserves the previously selected scope; unrelated unselected imports cannot switch the served city. Reimport after changing fixture data or the normalizer version. A GET request performs neither migration nor import.

The city API reads a consistent persisted export and reconstructs request-local projections. Restart requires PostgreSQL and its selected import, not local pointer files, the original fixture payload or normalizers. Old `current-import.json` files are ignored. Missing schema/imports make city endpoints return 503 with setup guidance; database failure never becomes a successful empty city. Retain complete fixture scopes; selective history pruning is unsupported. Alembic downgrade removes the CITY-04 tables and should only be used when intentionally resetting local fixture state.

`/health/ready` checks PostGIS and Redis only, without reading city history. It may return 200 before migration/import while city endpoints return 503. Redis remains outside the city query path.

Before upgrading observation storage, stop old API/import processes, run migration `0003_observation_codec`, and restart with the updated code. Existing valid selections need no reimport. The migration preserves unsupported older normalizer exports and rejects ambiguous or corrupt supported history; [storage compatibility and rollback](architecture/observation-storage.md) explains the checks.

Read [CITY-04](demos/city-04.md) for event/restart verification.

## Configuration boundaries

| Setting                                                         | Current consumer and behavior                                                         |
| --------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| `DATABASE_URL`, `REDIS_URL`                                     | API settings; read environment variables and root `.env`                              |
| `RAW_STORAGE_PATH`                                              | City API/worker settings read `.env`; city bundles use `<path>/city`. Original smoke worker uses process environment only; default `.local/raw` |
| `VITE_API_PROXY`                                                | Vite process environment; defaults to `http://127.0.0.1:8000`                         |
| `GOOGLE_CLOUD_PROJECT`, `BIGQUERY_DATASET`, `BIGQUERY_LOCATION` | dbt process environment; `.env` is not loaded by dbt                                  |
| `URBANPULSE_MODE`                                               | City settings accept only `fixture`; changing it does not enable live ingestion    |

The sample BigQuery location is a configuration example, not an approved cloud placement decision. Keep credentials outside the repository and frontend bundle.

## Checks and analytics smoke

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check.ps1
uv run --locked python scripts/smoke.py
```

For real spatial and browser checks, run `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check-city.ps1` with PostGIS running; keep ports 8011/5174 free. Chromium installation needs internet access. When running npm browser tests directly, first run `npm.cmd --prefix apps/web run test:e2e:install`; the locked Playwright version needs its own matching browser binaries ([official instructions](https://playwright.dev/docs/browsers)).

Stop host API/UI servers before the HTTP smoke command. It uses ports 8000 and 5173, verifies HTTP connectivity and stops its temporary servers. Logs are under `.local/smoke/`. It does not exercise a real browser or the database path. See [testing strategy](testing-strategy.md) for scope.

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

Shared configuration lives in `urbanpulse/config.py`. Follow the [CITY-01 walkthrough](demos/city-01.md) for the runnable map and [city MVP scenario](demos/city-mvp.md) for later cross-domain acceptance.

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

The optional development container command is `docker compose --profile app up -d --build --wait`. Stop host API/UI servers first to release ports 8000/5173. The image includes migrations; the one-shot `city-init` service migrates and imports before API startup. Initialization failure prevents dependent API startup. The initializer and API share PostgreSQL, not local files or a raw-data volume. API healthchecks use dependency readiness; verify city responses as well.

After updating fixture data on an existing stack, rerun `docker compose --profile app run --rm city-init`. It atomically selects the new complete import, visible to subsequent requests. API container recreation needs no reimport when the selected history remains in PostgreSQL. Apply migrations explicitly before host-based development as described above.

For isolated container validation, run `uv run --locked python scripts/compose_smoke.py`. This builds API/UI images, uses a unique Compose project and database volume with random loopback API/UI ports, verifies cold readiness and city 503 before setup, starts the full app profile, tests city/boundary/evidence through the API and UI proxy, recreates the API, and repeats initialization. It removes only that test stack and volume; logs remain in `.local/compose-smoke/`. CI runs the same script in its Compose job. Results and measured limits are in [Compose follow-up evidence](evidence/city-04-compose.md).

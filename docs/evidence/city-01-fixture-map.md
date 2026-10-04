# CITY-01 fixture map evidence

Date: 2026-10-05

Scope: the CITY-01 feature revision containing this record, based on `abde0144ae5f697c7642097e73ae44f78635cd6b`. Progress belongs in the [delivery plan](../delivery-plan.md); hosted run results are attached to the feature PR checks.

## Observed results

| Check | Observed result |
| --- | --- |
| `scripts/check.ps1` | Pass: Ruff lint/format, mypy (17 source files), 161 unit/API tests, ESLint, Prettier, TypeScript and Vite build |
| `uv run --locked pytest -m integration -q` | 7 passed against real local PostGIS 17 / extension 3.5 |
| `npm.cmd --prefix apps/web run test:e2e` | 5 Chromium tests passed against the production Vite build and real FastAPI/PostGIS |
| Visual inspection | Desktop 1440 px and mobile 390 px screenshots reviewed; map boundary rendered, markers selectable, panel/list usable and no horizontal overflow |
| External requests | Browser test observed no external HTTP requests during the fixture map flow |

Unit and integration markers deliberately run separately: the baseline deselects 7 integration cases, and the integration command deselects 161 unit/API cases. All selected cases passed.

Browser coverage includes keyboard selection with retained focus, marker/list synchronization, position movement, layer visibility, play/pause/reset, stale/expired/missing-time observations, unknown weather/planning, empty/outage scenarios, API retry, boundary failure with usable list, and mobile width. MapLibre workers are bundled as local assets; a development-only success is insufficient.

PostGIS coverage includes actual Southbank inside/edge/outside membership, invalid/empty/wrong-type/out-of-range geometry, capture-to-API replay and changed-boundary recomputation. The same revision and assessment rules used by the UI are exercised through the API.

## Reproduction and limits

Use the [CITY-01 walkthrough](../demos/city-01.md). Screenshots are generated under ignored `.local/city01/`, and browser failure traces under `apps/web/test-results/`. CI provisions PostGIS and uploads these browser artifacts.

The geometry is an attributed extract from the City of Melbourne CLUE small-area dataset. All transport events and stop/service facts are synthetic; no Transport Victoria key or live API was used. No cloud resources, numeric area-health score, production retention policy or persistent consumer ledger are established by these checks.

Two non-failing tooling notices remain: the existing Starlette/httpx test-client deprecation and Vite's large-chunk warning for the map bundle (about 365 kB gzipped for the main JavaScript asset, plus the local worker). This evidence does not measure production network performance or establish complete accessibility conformance.

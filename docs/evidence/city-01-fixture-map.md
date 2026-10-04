# CITY-01 fixture map evidence

Date: 2026-10-05

Scope: the CITY-01 feature revision containing this record, based on `abde0144ae5f697c7642097e73ae44f78635cd6b`. Progress belongs in the [delivery plan](../delivery-plan.md); hosted run results are attached to the feature PR checks.

## Observed results

| Check | Observed result |
| --- | --- |
| `scripts/check.ps1` | Pass: Ruff lint/format, mypy (18 source files), 178 unit/API tests, ESLint, Prettier, TypeScript and Vite build |
| `uv run --locked pytest -m integration -q` | 9 passed against real local PostGIS 17 / extension 3.5 |
| `npm.cmd --prefix apps/web run test:e2e` | 13 Chromium tests passed against the production Vite build and real FastAPI/PostGIS |
| Visual inspection | Desktop 1440 px and mobile 390 px screenshots reviewed; white/grey layout, text-only wordmark, tram icons and illustrative rails inspected; markers selectable, panel/list usable and no horizontal overflow |
| External requests | Browser test observed no external HTTP requests during the fixture map flow |

Unit and integration markers deliberately run separately: the baseline deselects 9 integration cases, and the integration command deselects 178 unit/API cases. All selected cases passed.

Browser coverage includes keyboard selection with retained focus, marker/list synchronization, position movement, locally loaded tram artwork, illustrative-track toggle, layer visibility, play/pause/reset, stale/expired/missing-time observations, unknown weather/planning, empty/outage scenarios, API retry, boundary failure with usable list, mobile width, no future resolution, retained disruption after outage, all missing-input explanations API-driven playback bounds, 15-second slider steps and all weather coverage states. MapLibre workers are bundled as local assets; a development-only success is insufficient.

PostGIS coverage includes actual Southbank inside/edge/outside membership, invalid/empty/wrong-type/out-of-range geometry, capture-to-API replay changed-boundary recomputation, cache reuse for identical spatial inputs, and outage replay beyond an unreceived resolution. The same revision and assessment rules used by the UI are exercised through the API.

## Reproduction and limits

Use the [CITY-01 walkthrough](../demos/city-01.md). Screenshots are generated under ignored `.local/city01/`, and browser failure traces under `apps/web/test-results/`. CI provisions PostGIS and uploads these browser artifacts.

The geometry is an attributed extract from the City of Melbourne CLUE small-area dataset. All transport events and stop/service facts are synthetic; no Transport Victoria key or live API was used. No cloud resources, numeric area-health score, production retention policy or persistent consumer ledger are established by these checks. ADR 0004 remains Proposed pending explicit architect acceptance.

Two non-failing tooling notices remain: the existing Starlette/httpx test-client deprecation and Vite's large-chunk warning for the map bundle (about 365 kB gzipped for the main JavaScript asset, plus the local worker). This evidence does not measure production network performance or establish complete accessibility conformance.


For this revision, `playwright install chromium` completed successfully in the local account, and all thirteen browser cases then executed against the production build. A separate account or environment must install the matching binaries using `npm.cmd --prefix apps/web run test:e2e:install`; the package lock alone does not supply a browser. Earlier five-case results were a prior checkpoint, not proof that every local environment has Chromium installed.


Final review regressions also verify stable interruption episode identity/start across updates and a new episode only after a received clear frame. Service-status TTL remains an explicit fixture limitation in ADR 0004; these results do not establish live service freshness.

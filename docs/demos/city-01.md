# CITY-01: Southbank fixture map

## Outcome and scope

Inspect Southbank tram observations on a map, advance a controlled clock and understand why area conditions differ from data coverage. The boundary is official City of Melbourne open data; vehicle IDs, positions, stops and service facts are synthetic.

The path is retained fixture bundle → CloudEvents validation/revision guard → PostGIS membership → area assessment → FastAPI → React/MapLibre. The original transport scenarios keep weather and planning unknown. Use the additional [CITY-02 weather scenarios](city-02.md) to inspect integrated warning behavior.

## Run

From the repository root, restore dependencies using [the development guide](../development.md). Start Docker Desktop, then:

```powershell
docker compose up -d --wait
uv run --locked python -m urbanpulse.adapters.city_store migrate
uv run --locked python -m workers.ingestion.main --city-fixture
uv run --locked uvicorn apps.api.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
npm.cmd --prefix apps/web run dev
```

Open [UrbanPulse](http://127.0.0.1:5173/?scenario=journey), or press the **Tram journey** scenario button. No provider key is required. The fixture import is required before serving. Rerun it after changing fixture files; GET requests never create captures or migrate the database.

## Walkthrough

1. At 0 seconds, identify the persistent synthetic label, Southbank outline and three tram markers. Tram 03 has no observation time and is Unknown. Overall conditions are Unknown because weather coverage is absent; planning has no as-of date.
2. Focus Tram 01 in the observations list and press Enter. Its marker and details select together. Clicking a marker selects the same list record.
3. Choose **30s · Position update**. Tram 01 moves to its next observed coordinate. **Play scenario** advances 15 fixture seconds every two real seconds after each response; Pause freezes it, Reset restores the initial view. The slider moves in 15-second increments to bound requests while scrubbing.
4. Choose **60s · Service interruption**. Tram 02 is now outside Southbank and disappears from the area view. The stop-based disruption remains applicable, so conditions become Degraded independently of vehicle location.
5. Choose **150s · Stale position**. Tram 01 is stale: its last observation was at 30 seconds. Weather and planning remain unknown. At 180 seconds a captured clear record is received; before that, no resolution time is exposed. After that record, conditions return to Unknown.
6. Choose **330s · Last known only**. Tram 01 has reached age 300 seconds. Its marker is removed, but its last-known observation remains in the list. Tram 03 stays labelled Time unknown.
7. Expand **Replay diagnostics**: at 330 seconds expect 5 applied, 1 duplicate, 1 superseded, 1 conflict and 1 invalid event. A retry with different trace context does not move a vehicle; an older/conflicting event cannot overwrite revision 2.
8. Select **Empty transport**: no markers or observations, no overall healthy claim. Select **Transport outage**: the 60-second interruption arrives before access fails at 90 seconds. At 200 or 330 seconds it remains Degraded with Error coverage, because the 180-second clear record was never received.
9. Toggle the tram, boundary and illustrative-track layers, inspect at a narrow mobile width, and open **View fixture evidence**. For an API failure demonstration, stop the API and choose an unvisited clock time; the UI shows an error and retry. Restart and retry.

The white/grey view uses a text-only UrbanPulse name and tram icons. Track lines are locally authored fixture illustrations, not real rail geometry or evidence of a measured route. Marker movement connects discrete observations visually. Nearby markers can overlap at low zoom: zoom in or use the equivalent list. The fixture deliberately makes no external map requests.

## Acceptance cases and verification

| Given / when | Then | Test boundary |
| --- | --- | --- |
| Official boundary; inside, exact-edge and outside points | Include inside/edge, exclude outside; reject invalid geometry | Real PostGIS integration |
| A geometry revision changes | Recompute membership and projection version | Real PostGIS integration |
| Same fixture and clock replayed after other requests | Identical snapshot; no cross-client clock state | Unit/API |
| Duplicate, older, conflicting or invalid position | One authoritative revision; explicit outcome counts | Unit and integration |
| Live/foreign event inserted into fixture | Withhold and count as rejected | Unit |
| Ages 119, 120, 299 and 300; missing/future time | Current, stale, stale, expired; unknown | Unit; browser at 120/300 age |
| Known disruption followed by outage at 90 seconds | No future resolution at 60; Degraded still at 200/330 because the clear frame was not received | Unit, PostGIS API and browser |
| Map/list selection, layer toggles, playback | Same selected identity; observed marker coordinates update | Chromium |
| API clock end differs from the default | Slider, playback and moment jumps respect the returned limit | Chromium |
| Empty data, API/boundary failure and mobile viewport | Explicit states, retry, usable list and no horizontal overflow | Chromium |

Run the baseline and CITY-01 suite:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check-city.ps1
```

To install the browser separately, run `npm.cmd --prefix apps/web run test:e2e:install` from the root before `npm.cmd --prefix apps/web run test:e2e`. Playwright requires browser binaries matching its locked package version; npm dependency installation alone does not install them.

The CITY check requires an already-running PostGIS. It installs Chromium if needed, runs integration tests and owns temporary API/UI servers on ports 8011/5174. Screenshots are saved under ignored `.local/city01/`; failure traces under ignored `apps/web/test-results/`. Linux CI runs the same tests with a PostGIS service.

## Storage and query details

The worker retains a canonical JSON bundle under `RAW_STORAGE_PATH/city/<sha256>.json` (default `.local/raw/city/`). The explicit import verifies the bundle and persists normalized domain exports in PostgreSQL; serving selects that immutable import through the local pointer. Event `capture_ids` are synthetic references within this bundle; they are not provider acquisition records. The evidence endpoint maps event IDs to those references and includes boundary attribution. Its clock/scenario query parameters restrict records to those already received, including service-status frames. Replaying a retained bundle recreates receipts; there is no persistent ledger or claim of crash-safe publication.

`GET /api/v1/areas/au-vic-melbourne-clue-southbank?seconds=30&scenario=journey` returns assessment, vehicles, coverage, clock, boundary/policy/projection versions and evidence links. Allowed seconds: integers 0–360; scenarios: journey, empty, outage. Geometry has its own revision-addressed URL. Positions are capped at 100 with explicit total/limit/truncated fields.

Projection version identifies the fixture bundle, geometry, policy and projection algorithm; evaluation time is separate. The adapter serves the current bundle; historical raw bundles can be retained locally, but a historical HTTP lookup is not part of this slice. Service coverage does not yet expire with age; `current` describes the latest complete fixture service snapshot. See the [service freshness limitation](../adr/0004-southbank-fixture-map.md#service-freshness-limitation) before interpreting it as live freshness. The empty scenario represents a complete synthetic transport snapshot. It does not establish what an empty provider response means.

Progress and remaining live-source decisions are tracked in the [delivery plan](../delivery-plan.md). [Evidence](../evidence/city-01-fixture-map.md) records actual test results.

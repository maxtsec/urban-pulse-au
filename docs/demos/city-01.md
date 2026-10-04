# CITY-01: Southbank fixture map

## Outcome and scope

Inspect Southbank tram observations on a map, advance a controlled clock and understand why area conditions differ from data coverage. The boundary is official City of Melbourne open data; vehicle IDs, positions, stops and service facts are synthetic.

The path is retained fixture bundle → CloudEvents validation/revision guard → PostGIS membership → area assessment → FastAPI → React/MapLibre. Weather and planning remain explicit unknown sections in the integrated city view.

## Run

From the repository root, restore dependencies using [the development guide](../development.md). Start Docker Desktop, then:

```powershell
docker compose up -d --wait
uv run --locked python -m workers.ingestion.main --city-fixture
uv run --locked uvicorn apps.api.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
npm.cmd --prefix apps/web run dev
```

Open [UrbanPulse](http://127.0.0.1:5173). No provider key is required. The API also initializes the same content-addressed bundle on first use if the worker step is omitted. Restart the API after changing fixture files.

## Walkthrough

1. At 0 seconds, identify the persistent synthetic label, Southbank outline and three tram markers. Tram 03 has no observation time and is Unknown. Overall conditions are Unknown because weather coverage is absent; planning has no as-of date.
2. Focus Tram 01 in the observations list and press Enter. Its marker and details select together. Clicking a marker selects the same list record.
3. Choose **30s · Position update**. Tram 01 moves to its next observed coordinate. **Play scenario** advances 15 fixture seconds every two real seconds after each response; Pause freezes it, Reset restores the initial view.
4. Choose **60s · Service interruption**. Tram 02 is now outside Southbank and disappears from the area view. The stop-based disruption remains applicable, so conditions become Degraded independently of vehicle location.
5. Choose **150s · Stale position**. Tram 01 is stale: its last observation was at 30 seconds. Weather and planning remain unknown. At 180 seconds the synthetic disruption resolves; conditions return to Unknown.
6. Choose **330s · Last known only**. Tram 01 has reached age 300 seconds. Its marker is removed, but its last-known observation remains in the list. Tram 03 stays labelled Time unknown.
7. Expand **Replay diagnostics**: at 330 seconds expect 5 applied, 1 duplicate, 1 superseded, 1 conflict and 1 invalid event. A retry with different trace context does not move a vehicle; an older/conflicting event cannot overwrite revision 2.
8. Select **Empty transport**: no markers or observations, no overall healthy claim. Select **Transport outage** at 60–179 seconds: the known interruption remains Degraded while transport coverage is Error.
9. Toggle the two layers, inspect at a narrow mobile width, and open **View fixture evidence**. For an API failure demonstration, stop the API and choose an unvisited clock time; the UI shows an error and retry. Restart and retry.

Marker movement connects discrete observations visually; it is not a measured route. Nearby markers can overlap at low zoom: zoom in or use the equivalent list. The fixture deliberately makes no external map requests.

## Acceptance cases and verification

| Given / when | Then | Test boundary |
| --- | --- | --- |
| Official boundary; inside, exact-edge and outside points | Include inside/edge, exclude outside; reject invalid geometry | Real PostGIS integration |
| A geometry revision changes | Recompute membership and projection version | Real PostGIS integration |
| Same fixture and clock replayed after other requests | Identical snapshot; no cross-client clock state | Unit/API |
| Duplicate, older, conflicting or invalid position | One authoritative revision; explicit outcome counts | Unit and integration |
| Live/foreign event inserted into fixture | Withhold and count as rejected | Unit |
| Ages 119, 120, 299 and 300; missing/future time | Current, stale, stale, expired; unknown | Unit; browser at 120/300 age |
| Known disruption and failed/missing source | Degraded with incomplete coverage; no false recovery | Domain and browser |
| Map/list selection, layer toggles, playback | Same selected identity; observed marker coordinates update | Chromium |
| Empty data, API/boundary failure and mobile viewport | Explicit states, retry, usable list and no horizontal overflow | Chromium |

Run the baseline and CITY-01 suite:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check-city.ps1
```

The CITY check requires an already-running PostGIS. It installs Chromium if needed, runs integration tests and owns temporary API/UI servers on ports 8011/5174. Screenshots are saved under ignored `.local/city01/`; failure traces under ignored `apps/web/test-results/`. Linux CI runs the same tests with a PostGIS service.

## Storage and query details

The worker retains a canonical JSON bundle under `RAW_STORAGE_PATH/city/<sha256>.json` (default `.local/raw/city/`). Reads verify its hash. Event `capture_ids` are synthetic references within this bundle; they are not provider acquisition records. The evidence endpoint maps event IDs to those references and includes boundary attribution. Replaying a retained bundle recreates receipts; there is no persistent ledger or claim of crash-safe publication.

`GET /api/v1/areas/au-vic-melbourne-clue-southbank?seconds=30&scenario=journey` returns assessment, vehicles, coverage, clock, boundary/policy/projection versions and evidence links. Allowed seconds: integers 0–360; scenarios: journey, empty, outage. Geometry has its own revision-addressed URL. Positions are capped at 100 with explicit total/limit/truncated fields.

Projection version identifies the fixture bundle, geometry, policy and projection algorithm; evaluation time is separate. The adapter serves the current bundle; historical raw bundles can be retained locally, but a historical HTTP lookup is not part of this slice. The empty scenario represents a complete synthetic transport snapshot. It does not establish what an empty provider response means.

Progress and remaining live-source decisions are tracked in the [delivery plan](../delivery-plan.md). [Evidence](../evidence/city-01-fixture-map.md) records actual test results.

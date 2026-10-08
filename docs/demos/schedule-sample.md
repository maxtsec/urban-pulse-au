# Public schedule sample

Open the root web page for **CBD + Southbank**. Trams use real schedules and routes but their positions are simulated. Buildings, streets, the river and DAM project records come from fixed government open-data snapshots. Weather is synthetic. Open **Sources & attribution** for the six dataset links, licences and modifications.

- Use 3D for surveyed building massing and illustrative tram/project models; 2D remains the accessible fallback.
- Select Trams to inspect scheduled trips; they are not observed vehicles. Ordinary 2D tram labels appear on hover, keyboard focus, selection or zoom 16 and above. Demo-affected trams have priority in label collision placement.
- The map initially shows only DAM `UNDER CONSTRUCTION` projects. **Layers → Other development projects** reveals other non-completed statuses; selecting a project in Works reveals that individual marker while development markers are enabled. All original statuses remain in Works; completed projects stay off the map. These display filters do not change area health.
- **Sample date → 7 Oct 2026 · Full-day history** unlocks the complete previous 24 hours, with distinct authored morning, midday, evening and late events. Use **8 Oct** for the current sample; **Go live** always returns to that date.
- Simulated Live starts at 10:00. History selects a two-hour window up to the advancing simulated edge. All 24 hours exist on each date; only the current sample day gates future windows.
- Area health explains authored demo conditions, separately for CBD and Southbank. Open `?demo=health` to jump to 09:15: CBD amber, Southbank red. Use **Explore the story** for calm, local impacts, major impacts, recovery and missing data. Click a reason to focus the map; the route list explains which simulated trips are highlighted.
- Yellow/red tram tint and halos mean **Demo delay**, not measured road congestion. Schedule motion remains unchanged. Green requires complete demo inputs; grey means insufficient inputs. Weather warnings may affect the demo state; project counts never do.
- **Layers → Main street names** toggles local labels in either view. Rails outside the two areas are hidden visually, while full paths remain available to the schedule simulation. The 2D helmet/plan markers describe DAM statuses; click for details.

## Day overview

Open **Day overview** beside the player for a 24-hour timetable. Separate CBD/Southbank tram rows show exact authored impact and coverage boundaries, including short severe-delay intervals. Weather uses the same synthetic readings as the map. The development row repeats one dated DAM snapshot; it does not assert operating hours. Clicking an elapsed block pauses at its start and opens the relevant information panel. On 8 October, future cells stay masked beyond simulated Live; 7 October is fully selectable. Narrow bands carry colour/symbols only, with exact times and readable text in the interval list. Escape closes the dialog and restores keyboard focus; mobile users can scroll the timetable horizontally.

The compact Area health panel shows **Demo affected trips**, with numerator/denominator at the selected instant. This is an authored-zone share of simulated trips, not a true delay rate. N/A means missing transport data or no trips. Expand **Method & area profile** for the definition, source completeness and dated DAM context.

## Mock trends and engineering walkthrough

**Data & pipeline → Trend preview** opens a frontend-only prototype with eight authored 15-minute intervals for 7 October, 08:00–10:00. Compare CBD/Southbank vehicle counts, select a bar for median position age and positions-capture coverage, and inspect partial/missing intervals. This fixed mock partition is independent of map time and area-health inputs. It does not fetch an API, run SQL or claim real collector statistics. Definitions inside the panel describe the mock; production metric semantics still need review with the actual mart.

**How it works** shows the intended raw → normalization → GCS → BigQuery/dbt → PostGIS/API path and three illustrative outcomes: a duplicate-free partition rerun, confirmation after a lost upload response, and a retained collection gap. Links lead to existing contracts and recovery documentation; they are not evidence that this end-to-end pipeline has executed. Replace the fixtures with a versioned serving response only after the real vertical slice is tested.

## Two-minute demonstration

| Time | Action | Explain |
| --- | --- | --- |
| 0:00–0:20 | Select 7 October; Area health → Rain + evening delays | Government map context with timetable-simulated movement and labelled demo impacts |
| 0:20–0:40 | Compare CBD and Southbank; select a delay reason | State, cause and affected-trip share are separate; click through to location |
| 0:40–1:00 | Select Missing data | N/A preserves uncertainty instead of inventing zero delays |
| 1:00–1:30 | Open Data & pipeline; compare the bars; select 08:45 and 09:00 | This mock previews future real trends, including partial and missing collection |
| 1:30–2:00 | Open How it works; select rerun and recovery examples | Explain the target pipeline and open the repo for actual implementation evidence |

Say explicitly that the trend values and engineering outcomes are mock examples. A future real-data presentation should identify its partition, source/capture times, quality results and reproducible run evidence before making analytical claims.

## Rebuild offline

From the repository root:

```powershell
uv sync --locked
uv run --locked python -m scripts.build_sample_dataset
uv run --locked pytest tests/test_sample_dataset.py -q
```

`sample-data/sources.zip` contains only approved public source inputs. Its exact members and hashes are in `sample-data/sources.lock.json`. The builder verifies them before use. It has no network access, credentials, collector-store writes or database dependency. The committed-output test rebuilds everything and compares bytes. Shapely is a development-only geometry dependency; the browser and capture image do not use it.

The manifest contains original source receipts where retained, GTFS outer ZIP and tram-member provenance, building survey dates, DAM modification date, query parameters, transformations, exclusions and derived hashes. The old GTFS download receipt did not record retrieval time; its HTTP Last-Modified is not a fabricated retrieval timestamp. New exports must supply their own receipts and pass review. Existing provenance stays unchanged.

The GTFS schedule includes equal minute-resolution times at some adjacent stops. Those positions change at the shared time; no false seconds/dwell measurements are invented. The schedule is not a guarantee of actual headways. The retained DAM pages were complete and provider metadata matched before/after; this is consistency evidence, not a provider transactional snapshot guarantee.

## Pages build and review

```powershell
cd apps/web
npm ci
npm run build -- --base=/urban-pulse-au/
npx playwright test --config=playwright.pages.config.ts
```

After merge/review, choose GitHub Pages **GitHub Actions** as the publishing source and run **Public static sample** on main. It tests the repository subpath, data-integrity failure, local assets and 3D before publishing `dist`. It needs only Pages deployment permissions, no GCP identity, backend, `.env` or key. A PR preview/build is not a published site. Re-run a reviewed main revision to replace a release; use a reviewed revert to roll back.

Pages uses the build's CSP meta policy; it cannot supply `frame-ancestors` or managed Caddy's security headers. Dataset links open only after a user follows them; automatic map requests remain same-origin. The old API walkthroughs use the separate test harness and are not shipped by this workflow.

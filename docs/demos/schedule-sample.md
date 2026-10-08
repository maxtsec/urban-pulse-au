# Public schedule sample

Open the root web page for **CBD + Southbank**. Trams use real schedules and routes but their positions are simulated. Buildings, streets, the river and DAM project records come from fixed government open-data snapshots. Weather is synthetic. Open **Sources & attribution** for the six dataset links, licences and modifications.

- Use 3D for surveyed building massing and illustrative tram/project models; 2D remains the accessible fallback.
- Select Trams to inspect scheduled trips; they are not observed vehicles. DAM status and source date are in Works; projects marked completed are retained in the list but excluded from map models.
- Simulated Live starts at 10:00. History selects a two-hour window up to the advancing simulated edge. All 24 hours exist in the dataset; the existing Live/history control policy still gates future windows.
- Area health explains authored demo conditions, separately for CBD and Southbank. Open `?demo=health` to jump to 09:15: CBD amber, Southbank red. Use **Explore the story** for calm, local impacts, major impacts, recovery and missing data. Click a reason to focus the map; the route list explains which simulated trips are highlighted.
- Yellow/red tram tint and halos mean **Demo delay**, not measured road congestion. Schedule motion remains unchanged. Green requires complete demo inputs; grey means insufficient inputs. Weather warnings may affect the demo state; project counts never do.
- **Layers → Main street names** toggles local labels in either view. Rails outside the two areas are hidden visually, while full paths remain available to the schedule simulation. The 2D helmet/plan markers describe DAM statuses; click for details.

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

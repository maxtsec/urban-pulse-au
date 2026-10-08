# ADR 0022: Public mixed-source schedule sample

Status: Accepted by the project architect on 2026-10-08. Feature implementation and public deployment follow PR review.

## Decision

Replace fabricated public trams and development projects with a reproducible **CBD + Southbank** static sample, suitable for GitHub Pages. Keep the API-backed 360-second fixtures as isolated test inputs. The protected Cloud Run backend and home collector are unchanged.

| Layer | Source and meaning |
| --- | --- |
| Buildings | Historical City of Melbourne Structure footprints, with surveyed relative heights; retain original capture dates |
| Tracks and routes | Fixed tram GTFS Schedule member; full shapes intersecting the two accepted CLUE areas |
| Tram positions | **Schedule simulation, not live**; select service calendar and exceptions for 8 October 2026, including previous service-day trips after midnight; interpolate distance between scheduled departure and next arrival, hold during scheduled dwell |
| Development | Retained complete DAM snapshot, original status and source modification date; missing or out-of-area coordinates do not become invented sites |
| Weather | Explicitly synthetic sunny/cloudy/rainy day |
| Streets / river | Accepted option B: local Vicmap Transport Road Line and Vicmap Hydro Water Polygon, clipped to display bounds; no runtime tile server |

These six government datasets are attributed under CC BY 4.0. GTFS realtime data is excluded. The schedule sample does not assess observed punctuality, actual fleet size, current area health or real construction impacts. A crane represents the DAM `UNDER CONSTRUCTION` status, not a verified worksite position. The sample clock does not reconstruct historical DAM/building states.

## Determinism and limits

Retain the licensed public inputs in a hash-pinned source archive outside the web build. `scripts/build_sample_dataset.py` runs offline, rejects changed source inventory, verifies complete DAM pages against before/after metadata, validates geometry and outputs canonical JSON with byte lengths and SHA-256. Store all derived file hashes, source receipts, transformations and credits in the manifest. Never substitute generated vehicles/projects when loading fails.

The fixed calendar date is a 24-hour Melbourne civil day without a daylight-saving transition. GTFS times beyond 24:00 retain their service date. A scheduled trip instance is not a known physical vehicle. Published equal timestamps at different stops are instantaneous transitions: use the last scheduled stop at that timestamp; do not invent dwell seconds. Full shapes are used for motion; only positions within the CLUE union appear. There are no received realtime observations and no MAP-02 observation-delay claim.

Road centre lines are visual context, not widths or navigable routes. Hydro watercourse polygons are not flood extents. The display clip rectangle does not expand analytical area membership. Keep same-origin assets, local font rendering and no secrets. Each generated data file is capped at 12 MiB. Buildings load only when needed in 3D. Refreshes are reviewed dataset-version changes.

## Playback and deployment

The existing simulated Live/History interaction remains: simulated Live starts at 10:00 per page session; two-hour History windows cannot run beyond that advancing edge. The dataset itself contains all 24 hours. Explicit schedule/synthetic labels replace the blanket synthetic-data claim. No numerical health score is added.

Pages publishes only the production `dist` artifact, from reviewed main through a manual workflow; it has no backend or cloud identity. Test the `/urban-pulse-au/` base path with no API and no external asset requests before deployment. Generated filenames carry build hashes and manifest checks protect mismatched data. Rollback republishes a reviewed commit.

Production builds insert a CSP meta element before scripts. [CSP meta restrictions](https://www.w3.org/TR/CSP3/#meta-element) mean `frame-ancestors`, `sandbox` and reporting directives cannot be enforced there; do not claim Pages provides the managed Caddy response-header protections. Caddy retains its stronger headers. See [Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits); the source archive is never part of the website artifact.

This supersedes ADR 0020's fabricated tram/project sources for the public view. Its playback, panel, reduced-motion and recovery rules remain. It does not replace MAP-02's realtime animation contract or authorize publishing realtime capture history.

# ADR 0022: Public mixed-source schedule sample

Status: Accepted by the project architect on 2026-10-08. Feature implementation and public deployment follow PR review.

## Decision

Replace fabricated public trams and development projects with a reproducible **CBD + Southbank** static sample, suitable for GitHub Pages. Keep the API-backed 360-second fixtures as isolated test inputs. The protected Cloud Run backend and home collector are unchanged.

| Layer | Source and meaning |
| --- | --- |
| Buildings | Historical City of Melbourne Structure footprints, with surveyed relative heights; retain original capture dates |
| Tracks and routes | Fixed tram GTFS Schedule member; full shapes intersecting the two accepted CLUE areas |
| Tram positions | **Schedule simulation, not live**; select service calendar and exceptions independently for 7 and 8 October 2026, including previous service-day trips after midnight; interpolate distance between scheduled departure and next arrival, hold during scheduled dwell |
| Development | Retained complete DAM snapshot, original status and source modification date; missing or out-of-area coordinates do not become invented sites |
| Weather | Explicitly synthetic sunny/cloudy/rainy day |
| Streets / river | Accepted option B: local Vicmap Transport Road Line and Vicmap Hydro Water Polygon, clipped to display bounds; no runtime tile server |

These six government datasets are attributed under CC BY 4.0. GTFS realtime data is excluded. The schedule sample does not assess observed punctuality, actual fleet size, current area health or real construction impacts. A crane represents the DAM `UNDER CONSTRUCTION` status, not a verified worksite position. The sample clock does not reconstruct historical DAM/building states.

## Determinism and limits

Retain the licensed public inputs in a hash-pinned source archive outside the web build. `scripts/build_sample_dataset.py` runs offline, rejects changed source inventory, verifies complete DAM pages against before/after metadata, validates geometry and outputs canonical JSON with byte lengths and SHA-256. Store all derived file hashes, source receipts, transformations and credits in the manifest. Never substitute generated vehicles/projects when loading fails.

Both fixed dates are 24-hour Melbourne civil days without a daylight-saving transition. GTFS times beyond 24:00 retain their service date. A scheduled trip instance is not a known physical vehicle. Published equal timestamps at different stops are instantaneous transitions: use the last scheduled stop at that timestamp; do not invent dwell seconds. Full shapes are used for motion; only positions within the CLUE union appear. There are no received realtime observations and no MAP-02 observation-delay claim.

Road centre lines are visual context, not widths or navigable routes. Hydro watercourse polygons are not flood extents. The display clip rectangle does not expand analytical area membership. Keep same-origin assets, local font rendering and no secrets. Each generated data file is capped at 12 MiB. Buildings load only when needed in 3D. Refreshes are reviewed dataset-version changes.

## Playback and deployment

For 8 October, simulated Live starts at 10:00 per page session and history cannot exceed that advancing edge. The separate 7 October sample allows every two-hour window across the full 24 hours. Returning to Live selects 8 October; completing the previous day does not silently switch dates. Explicit schedule/synthetic labels replace the blanket synthetic-data claim. No numerical health score is added.

Pages publishes only the production `dist` artifact, from reviewed main through a manual workflow; it has no backend or cloud identity. Test the `/urban-pulse-au/` base path with no API and no external asset requests before deployment. Generated filenames carry build hashes and manifest checks protect mismatched data. Rollback republishes a reviewed commit.

Production builds insert a CSP meta element before scripts. [CSP meta restrictions](https://www.w3.org/TR/CSP3/#meta-element) mean `frame-ancestors`, `sandbox` and reporting directives cannot be enforced there; do not claim Pages provides the managed Caddy response-header protections. Caddy retains its stronger headers. See [Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits); the source archive is never part of the website artifact.

This supersedes ADR 0020's fabricated tram/project sources for the public view. Its playback, panel, reduced-motion and recovery rules remain. It does not replace MAP-02's realtime animation contract or authorize publishing realtime capture history.

## Accepted area-health presentation amendment — 2026-10-08

The architect accepted **state + reasons**, separately for CBD and Southbank: green means both demo inputs are available with no known demo impact; amber means a local impact; red means a major interruption; grey means incomplete inputs without a confirmed impact. A confirmed adverse impact takes precedence over missing coverage, which remains visible separately. This is authored sample behaviour, not a numeric health score or a change to production area policy.

The sample includes local CBD delays, severe Southbank delays, a Southbank weather warning, recovery and a missing-transport interval. Each impact has a half-open validity interval and a location. Selecting a reason focuses the map. A visit summary, highlighted route list and last/next **scripted** change explain the current state. Future changes are demo navigation, not predictions. Rain animation itself does not create a warning; DAM counts never lower health.

Yellow/red tram highlights in both views identify scheduled vehicles inside an authored 650 m transport-impact zone **and that impact's CLUE area** during its validity. They are labelled Demo delay; they do not measure congestion, change scheduled movement or assert observed delays. Weather-only impacts do not colour trams. The same classification supplies flat markers, 3D tint/halo, route list and detail text. Event ends remove highlights deterministically when seeking or playing.

Only **drawn** rails are clipped to the CBD + Southbank union. Full GTFS shapes and distance indices remain intact for motion. Separate area outlines, restrained status fills and an outside-area mask keep focus. A switchable main-street-name layer uses retained Vicmap names with in-area anchors and no external glyph/tile requests. In 2D, a helmet denotes DAM UNDER CONSTRUCTION; a plan icon denotes another non-completed development status, never a verified obstruction.

## Accepted affected-trip share and previous day — 2026-10-08

The architect accepted **Demo affected-trip share**: at the selected instant, count unique scheduled trip-instance IDs inside the selected CLUE area and a currently active authored transport-impact zone, divided by all unique scheduled trip instances inside that area. Display numerator, denominator and a whole-number rounded percentage. Empty denominators or missing transport coverage produce N/A; unavailable counts are not presented as zero. This is neither observed lateness nor an interval average, and does not determine area status. Weather warnings and DAM counts do not enter this ratio.

Add a complete previous sample day (7 October) with separately calendar-selected GTFS trips and preceding service-day carry-over. Its authored conditions include morning delays, midday interruption, afternoon rain/warnings, evening delays, missing inputs and late recovery. Synthetic conditions remain explicitly labelled; this is not captured historical telemetry. Reuse the same dated buildings/DAM source snapshots, without fabricating daily construction changes or working hours. The previous schedule has its own manifest hash and stays below the existing per-file size cap; source archive inputs are unchanged.

The day overview uses accurately sized colour bands with accessible labels, and a separate wrapping interval list for readable text and larger navigation targets. Closing remains available while scrolling. Day selection preserves the map instance; the source-backed schedule, authored conditions, weather, percentage and timetable all use the same selected sample date.


## Frontend pipeline preview — 2026-10-08

The architect requested a frontend mock before connecting real pipeline results. Add a separately labelled trend preview with fixed authored 15-minute counts, freshness and capture gaps, plus an intended-flow explanation and illustrative rerun/recovery outcomes. This does not approve production metric SQL, assert that the pipeline has run, or change map health. The preview is independent of the selected map clock. Existing implementation evidence stays in the repository; links distinguish it from illustrative outcomes.

Default map presentation prioritises affected trams and DAM construction status. Other projects remain selectable in Works or through a layer toggle; ordinary route labels appear on interaction or close zoom. These are display choices, with no change to source records or analytical membership.

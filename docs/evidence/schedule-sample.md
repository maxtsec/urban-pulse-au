# Mixed-source schedule sample evidence

Measured 2026-10-08. Scope and interpretation: [ADR 0022](../adr/0022-public-schedule-sample.md). Reproduction: [walkthrough](../demos/schedule-sample.md).

| Retained output | Measurement |
| --- | --- |
| Licensed source archive, excluded from website | 16,759,478 bytes |
| City/schedule JSON | 9,133,337 bytes; about 1.33 MB gzip in Vite's report |
| Previous-day schedule JSON | 8,221,545 bytes; separate hash-pinned 7 October calendar export, 4,539 trip instances |
| On-demand building geometry | 3,340,553 bytes |
| Entire static build, before HTTP compression | 24,715,017 bytes |
| Fixed-day trips / used full shapes | 4,539 / 84 |
| DAM records | 463; 108 non-completed, spatially applicable records have map models |
| Local street features / river polygon | 3,181 / 1 |
| CBD building source polygons | 4,587; 4,441 valid Structure polygons; 2 invalid Structure records rejected without invented heights |
| Southbank building source polygons | 1,189; 1,108 valid Structure polygons |

Source pack and every member are hash-pinned. Generated JSON is canonical and compared byte-for-byte by the offline rebuild test. Builder environment: CPython 3.12.15, Shapely 2.2.0, GEOS 3.14.1. This describes build tooling, not a deployed collector host. The committed manifest records input and output hashes, query receipts, dates, transformation counts and six dataset credits.

Validation performed:

- Ruff lint/format and existing strict mypy scope passed.
- Repository Python suite: 882 passed, 181 platform/fixture skips, 190 integration tests deselected. A subsequent additional DAM consistency regression passed with the five-test builder suite.
- Frontend lint/format, TypeScript and 29 unit tests passed, including schedule dwell, equal timestamps, midnight service instances and seek/play determinism.
- Initial full browser run: 70 passed, 2 intentional performance skips, 2 failures at the old five-second 3D readiness timeout. CBD adds substantially more geometry than the old Southbank fixture. Non-completed projects are the only map models; readiness assertions are bounded at 15 seconds, with 60 seconds for the multi-stage context-loss test. Static fallback markers remain while loading. This is functional verification, not a frame-rate acceptance claim.
- Final isolated explorer rerun: all 13 tests passed after the changes.
- Final compiled Caddy serving: 19 browser tests passed, including every explorer case, model failure, continuous Live, 2D/3D re-entry, context recovery, keyboard/mobile, CSP and backend semantics. Database/API outage and recovery passed; smoke containers, networks and volumes were removed.
- Pages production base-path build: two tests passed, covering local-only 3D assets, six credits, no API calls and rejected corrupt data. No backend ran for these tests.
- Real/adversarial Docker build contexts passed the exact allowlist inventory check. Public source ZIP, credentials and tests are excluded from the image.
- Pages workflow passed actionlint; 378 changed-document local link targets resolved before adding this evidence page.

Limits: the complete schedule has 24 hours, while the retained simulated Live/history UI still gates future windows. Minute-resolution stop times can create instantaneous changes at equal timestamps. The sample is not actual fleet telemetry, historical construction reconstruction, routing, flood coverage or a current health assessment. Pages publication itself remains a post-review action. CSP meta cannot enforce frame-ancestors; managed Caddy retains its header protection. Vite reports large JS chunks; cold 3D loading and device performance remain visible trade-offs rather than claimed performance guarantees.

### Area-health and map-focus review additions

The display-only track builder clips drawn lines to the CLUE union without modifying the full schedule shapes or distance indices. The seven-test builder suite passes, including byte-identical rebuild and display-boundary checks. Frontend checks pass: ESLint, Prettier, TypeScript, production build and 34 unit tests. Added tests cover half-open event validity, separate area states, adverse impacts with missing coverage, deterministic seeking and area-scoped delay highlights.

Four Pages browser cases pass: original offline/integrity checks plus demo-state navigation, reason focus, recovery, missing coverage, street-name toggle, replacement project icons, tram explanation and 2D/3D re-entry. Screenshots were inspected in both views. Yellow/red model tint and halos are authored demo conditions; no congestion measurement is claimed. Real and adversarial Docker contexts pass the exact allowlist check with the new components and SVGs.

The updated compiled Caddy browser suite passes all 19 cases, including the fixed panel, zoom controls, mobile resize, model-loading failure and WebGL recovery. Repository Ruff lint/format and strict mypy scope (85 files) also pass after these additions.

### Day overview addition

The timetable derives traffic intervals from the same authored transport events/coverage gaps, weather from the existing synthetic readings, and development from the dated DAM snapshot. It clips all selectable intervals at simulated Live and does not reveal later weather or incident endpoints. Three new unit tests verify contiguous elapsed coverage, short disruptions, domain separation and future gating (37 total frontend unit tests pass).

Six Pages browser cases now pass, including timetable-to-map navigation, weather/project tabs on mobile, Escape and focus restoration. The first mobile run exposed the inherited hidden help-label style; the overview button now has explicit mobile visibility and the affected suite passes. Lint/format and the production build pass. The earlier 19-case Caddy rehearsal is retained above; it preceded this timetable-only addition.

### Previous day and affected-trip share

The 7 October calendar is generated independently, including 6 October service-day carry-over. Eight builder tests pass, now comparing every manifest-listed file byte-for-byte. The fixed input happens to produce 4,539 trips on both civil days; distinct service dates/IDs are retained rather than relabelling current-day trips. Shapes are identical across these two retained calendars, verified by test. The extra uncompressed schedule is about 8.22 MB (about 1.21 MB gzip); the complete static artifact grows to about 24.72 MB. No file exceeds the 12 MiB dataset cap.

Forty frontend unit tests pass, including unique local denominators, missing/empty N/A, weather exclusion, day-specific conditions and previous-day seek determinism. Eight Pages browser cases pass, covering previous-day 24-hour access, map preservation on date change, return to bounded current-day Live, midnight playback completion, short-event navigation, mobile tabs, corrupt data and 2D/3D models. Screenshots were inspected for the compact percentage panel and expanded interval list. On the 390 px mobile viewport the document width remains 390 px and the close button remains a visible 44 x 44 px target after scrolling to the bottom.

Ruff lint/format, mypy (85-file scope), frontend lint/format and production build pass. Both actual and adversarial Docker contexts pass the updated allowlist inventory. The metric and authored history are presentation samples, not measured delay performance or captured history; the unchanged DAM snapshot asserts no daily working hours.

The final compiled Caddy rehearsal was rerun after these changes: all 19 browser cases passed, followed by API/database outage and recovery. Smoke resources were removed successfully.

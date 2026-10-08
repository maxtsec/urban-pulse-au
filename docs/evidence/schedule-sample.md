# Mixed-source schedule sample evidence

Measured 2026-10-08. Scope and interpretation: [ADR 0022](../adr/0022-public-schedule-sample.md). Reproduction: [walkthrough](../demos/schedule-sample.md).

| Retained output | Measurement |
| --- | --- |
| Licensed source archive, excluded from website | 16,759,478 bytes |
| City/schedule JSON | 8,928,382 bytes; about 1.31 MB gzip in Vite's report |
| On-demand building geometry | 3,340,553 bytes |
| Entire static build, before HTTP compression | 16,257,158 bytes |
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

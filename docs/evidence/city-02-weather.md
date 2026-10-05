# CITY-02 weather fixture evidence

Date: 2026-10-05. Scope: synthetic Southbank weather replay on Windows, local PostGIS and Chromium. Source policies: ADR 0005 and ADR 0006. [Delivery status](../delivery-plan.md) and [reproduction](../demos/city-02.md).

## Verified behavior

- Captured raw weather fixtures normalize to typed CloudEvents and feed Location Intelligence without provider requests. Checksummed retained bundles reproduce the same result after rewind/restart.
- Modelled readings and Advice do not create adverse facts. Applicable Watch and Act/Emergency Warning records do; cancellation removes only that warning's reason.
- At the expiry boundary, stale or error coverage leaves Unknown. Source outage suppresses future cancellation/captures while preserving effective known warnings.
- Identical payload recapture advances original receipt evidence without changing warning issue/update time, revision or event provenance. Malformed captures cannot partially apply or advance receipt time, including non-array payloads and non-object records before or after valid records. Both area and evidence endpoints preserve explicit rejection results.
- Unknown severity/geometry, partial product scope and unresolved omission prevent complete coverage. Expiry alone cannot repair it.
- Evidence regression tests distinguish missing capture IDs from corrupt references, verify matching snapshot/evidence timelines and prohibit projection/database work on the evidence path. Complete pilot coverage accepts additional declared products.
- Real PostGIS verifies positive-area overlap, containment, edge/vertex exclusion, holes, disconnected polygons and invalid geometry. Spatial memoization follows both geometries.
- Chromium verifies the map/list lifecycle, two-domain reasons, warning-layer visibility, original receipt date/timezone, credits, mobile width and no external fixture requests. Additional UI checks verify weather visibility without scrolling at desktop/mobile sizes, compact independent panel stacks and keyboard scenario selection with clock preservation, missing-reading weather views, separate weather duplicate counts, scenario URL/history/reload behavior and map canvas/camera preservation across a delayed scenario switch. Desktop/mobile screenshots were inspected and are available in the CI city-browser-evidence artifact.

## Checks

Local checks: 250 unit/API tests, 19 real PostGIS integration tests and 24 Chromium end-to-end tests. Ruff lint/format, strict mypy, ESLint, Prettier and production build pass. The feature PR links its independent CI run. Run `scripts/check.ps1` and `scripts/check-city.ps1` from the repository root. No dependencies or migrations are added.

## Limits

These are authored records, geometries and complete-snapshot assertions, not verified Open-Meteo/VicEmergency responses. No live provider, cloud capture, hosted deployment or numerical freshness TTL is enabled. Shared in-process delivery and persistent cross-domain reconciliation remain CITY-04 work. The warning geometry policy is independent of [ADR 0004](../adr/0004-southbank-fixture-map.md). Existing MapLibre bundle-size and Starlette/httpx deprecation warnings remain non-fatal.

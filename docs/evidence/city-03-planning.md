# CITY-03 planning fixture evidence

Date: 2026-10-05. Scope: authored DAM-shaped snapshots, local PostGIS and Chromium on Windows. [ADR 0007](../adr/0007-planning-fixture-profile.md) owns the accepted policy; [delivery status](../delivery-plan.md) and [reproduction](../demos/city-03.md) are maintained separately.

## Verified behavior

- Retained planning payloads normalize to CloudEvents with stable scope, unique development keys, explicit source dates and capture references. Replaying the retained bundle after rewind or service reconstruction produces identical results.
- Complete snapshots apply atomically. Partial, malformed and failed captures preserve the last complete profile and receipt. Missing records leave the current list only on a successful complete replacement; previous status/date survive in history without invented cancellation or completion. Complete-empty and missing snapshots remain distinct, and reappearing keys return to the current list.
- Revision receipts prevent duplicate effects, unseen older revisions and changed historical event identities. Snapshot identity reuse, source-date rollback and unknown dates are covered. Record ordering does not change the validated snapshot fingerprint.
- Whole-fixture spatial uncertainty includes current unlocated records labelled Southbank, Carlton or no area. Capture acceptance is reported independently, and browser tests distinguish successfully accepted location gaps from retained data after rejection. Outage demo moments match the received timeline.
- Shared capture timing/history is exercised by both weather and planning; abandoned candidates do not leak events or provenance. The scenario registry is checked against both API endpoints, evidence and the published schema. Transport empty/outage behavior follows policy metadata in both snapshot and evidence replay, including when assigned to another scenario name. Planning fingerprints each incoming event once and retains the latest receipt.
- Unchanged recapture advances receipt only. Evidence follows the selected replay clock and does not run planning projections or spatial queries. Corrupt references return 503; unknown capture IDs return 404.
- Real PostGIS confirms three included synthetic Southbank sites, excluded outside points, edge/vertex inclusion and no buffer. Missing coordinates do not appear on the map or in the area count; membership is recomputed when locations change.
- Planning changes, coverage gaps and outages leave current conditions/reasons unchanged when transport/weather inputs are fixed. The 270s planning-outage case preserves Normal current conditions while showing error coverage and the original planning snapshot.
- Chromium verifies the integrated default view, map/list keyboard selection, layer toggles, original statuses, separate snapshot/receipt dates, partial/absence/outage/recovery states, diagnostics and evidence. The default weather summary remains above the fold at mobile width. Desktop/mobile screenshots were inspected and are included in CI's city-browser-evidence artifact.

## Checks

Local checks: 315 unit/API tests, 25 real PostGIS integration tests and 32 Chromium end-to-end tests. Ruff lint/format, strict mypy, ESLint, Prettier and production build pass. Run `scripts/check.ps1` and `scripts/check-city.ps1`; the feature PR links independent CI results. No dependencies, migrations or cloud resources are added.

## Limits

Development records and dates are synthetic, not verified municipal snapshots. Complete coverage means the authored pilot sample, not every development or roadwork. Live source identity, retention and numerical freshness remain SRC-02 work. This request-local replay is reconstructed from retained snapshots; shared in-process publication/handlers and persisted domain state remain CITY-04. Existing MapLibre bundle-size and Starlette/httpx deprecation warnings are non-fatal.

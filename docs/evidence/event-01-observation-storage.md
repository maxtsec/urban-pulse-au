# EVENT-01 observation storage evidence

Date: 2026-10-05. Input baseline: PR #9, `1bbdd70`. Scope: normalized synthetic fixture history in real PostgreSQL/PostGIS.

## Compatibility and failures

Seven migration tests use isolated schemas and an independent legacy-row writer. Supported imports preserve revision-envelope bytes, fingerprints, metadata, content hash and active selection. Restored transport/weather/planning rows match the original normalized rows, including weather warning history and retransmission trace context. City snapshots agree at clocks 0, 60, 150, 180, 240, 270 and 360. Reimport retains the same scope.

Safe upgrade/downgrade/upgrade round trips reproduce the legacy database contents exactly. Ambiguous descriptors, missing revisions, malformed event slots and checksum mismatches roll back schema and data. Literal reference-looking evidence survives upgrade and correctly blocks unsafe downgrade. An unsupported older normalizer remains unchanged and unavailable.

The local development database contained both an unsupported normalizer-v1 import and a selected valid v2 import. Upgrade preserved the former, converted the latter and served the city at 360 seconds after API restart without recapture or reimport.

## Checks

Ruff lint/format, mypy, web lint/format and production build passed. The unit/API suite passed 363 tests and the real PostGIS integration suite passed 51 tests. All 32 Chromium Playwright tests passed. The isolated Compose smoke also passed under `python -O`: fresh migration/import, city/boundary/evidence responses, UI proxy, API recreation and repeated initialization. Its test stack and volume were removed.

## Limits

This verifies versioned observation persistence and compatibility. Persistent publication, delivery leases, consumer receipts, dead-letter/replay and worker crash recovery belong to the following EVENT-01 implementation steps; these storage tests do not establish those delivery guarantees.

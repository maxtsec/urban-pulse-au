# CITY-04 verification evidence

Date: 2026-10-05. Scope: local synthetic Southbank replay through PostgreSQL exports, in-process event handlers and real PostGIS.

## Checks

- Ruff lint/format and strict mypy passed.
- 332 unit/API tests passed, including atomic candidate-state rollback, bounded retries, independent clocks, typed service identity, expiry and semantic transition suppression.
- 37 real PostGIS integration tests passed. The 12 new persistence cases cover all seven scenarios against the original fixture path, duplicate/concurrent imports, whole-import rollback, original trace context, content integrity and fresh-process recovery without raw fixture reads or normalizers.
- Frontend ESLint, Prettier, TypeScript and production build passed.
- All 32 Chromium e2e tests passed. The clock-limit interceptor now awaits cached-clock refetches before another jump/teardown; its focused case also passed three consecutive runs.

A first local end-to-end reconstruction at the complete 360-second city clock took approximately 0.54 seconds, including input load and spatial work. This is one workstation sample, not a latency target or capacity result. Repeated checkpoint reconstruction is intentionally bounded to this fixture and remains a scaling trade-off.

## Limits

Tests use synthetic records, authored coverage checkpoints and existing spatial/fixture policies. They do not establish live source freshness/completeness, accepted transport thresholds under ADR 0004, cloud readiness, a durable consumer ledger or notification delivery. Persistent state consists of complete normalized input history; handler effects and receipts are disposable. Existing nonfatal build warnings concern bundle size and the Starlette/httpx test-client deprecation.

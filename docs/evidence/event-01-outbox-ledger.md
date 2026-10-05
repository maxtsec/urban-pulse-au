# EVENT-01 outbox and ledger evidence

Date: 2026-10-05. Baseline: `4fe7170` (PR #10). Scope: additive PostgreSQL transaction and repository primitives using synthetic CloudEvents.

## Database behavior

Twenty-five integration cases use isolated schemas and real concurrent connections. They verify atomic owner/publication writes, immutable first-envelope retention, concurrent publication deduplication, frozen consumer registration, distinct claims across workers, nonblocking selection around a locked delivery, independent consumer progress and context isolation.

Effect tests commit a real database row with its receipt/cursor and a derived publication. Injected exceptions roll all of them back; swallowed operation errors still abort the unit of work. Duplicate and superseded revisions skip effects, and changed content under an old ID conflicts before revision ordering. Retrying completion after commit produces no second effect, including conflict dead letters. Forged claim identity and attempts-exhausted completion remain rejected.

Lease tests retain attempt history across repository instances, reject a replaced generation or mismatched context/consumer, roll back work that exceeds its lease, and dead-letter a delivery after three expired attempts on the next claim sweep. These are database-boundary tests; no production worker or external notification is exercised.

An upgrade test starts at `0004` with three recorded attempts, upgrades to `0005`, and successfully completes a fourth attempt under a test-only larger application limit. Negative counters remain rejected. A downgrade with a counter above three fails without losing the schema version or history. Production policy remains three attempts.

## Verification results

- Ruff lint/format and mypy passed; web ESLint, Prettier and the production build passed.
- Unit/API suite: 372 passed.
- Real PostgreSQL/PostGIS integration suite: 76 passed, including 25 new outbox/ledger cases.
- Playwright browser suite: 32 passed at the initial PR checkpoint; these backend review fixes leave browser/API behavior unchanged. Lint, type/build, unit/API, integration and Compose checks were rerun for the fixes.
- Compose smoke passed under `python -O`: cold readiness, initialization/migration, city/boundary/evidence endpoints, web proxy, API recreation and repeated initialization. The isolated stack and volume were removed afterward.

## Limits

Retry scheduling, a continuously running worker, operator replay/backfill, structured inspection commands, fixture checkpoint barriers and real process-crash injection remain the next implementation slices. Browser/API reads still use the existing isolated in-process replay. No live source collection or cloud provisioning is enabled.

# EVENT-01 outbox and ledger evidence

Date: 2026-10-05. Baseline: `4fe7170` (PR #10). Scope: additive PostgreSQL transaction and repository primitives using synthetic CloudEvents.

## Database behavior

Twenty-two integration cases use isolated schemas and real concurrent connections. They verify atomic owner/publication writes, immutable first-envelope retention, concurrent publication deduplication, frozen consumer registration, distinct claims across workers, nonblocking selection around a locked delivery, independent consumer progress and context isolation.

Effect tests commit a real database row with its receipt/cursor and a derived publication. Injected exceptions roll all of them back; swallowed operation errors still abort the unit of work. Duplicate and superseded revisions skip effects, and changed content under an old ID conflicts before revision ordering. Retrying completion after commit produces no second effect.

Lease tests retain attempt history across repository instances, reject a replaced generation or mismatched context/consumer, roll back work that exceeds its lease, and dead-letter a delivery after three expired attempts on the next claim sweep. These are database-boundary tests; no production worker or external notification is exercised.

## Verification results

- Ruff lint/format and mypy passed; web ESLint, Prettier and the production build passed.
- Unit/API suite: 372 passed.
- Real PostgreSQL/PostGIS integration suite: 73 passed, including 22 new outbox/ledger cases.
- Playwright browser suite: 32 passed.
- Compose smoke passed under `python -O`: cold readiness, initialization/migration, city/boundary/evidence endpoints, web proxy, API recreation and repeated initialization. The isolated stack and volume were removed afterward.

## Limits

Retry scheduling, a continuously running worker, operator replay/backfill, structured inspection commands, fixture checkpoint barriers and real process-crash injection remain the next implementation slices. Browser/API reads still use the existing isolated in-process replay. No live source collection or cloud provisioning is enabled.

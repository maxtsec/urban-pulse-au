# EVENT-01 worker recovery evidence

Date: 2026-10-05. Baseline: `d1f118d` (PR #11). Scope: synthetic database effects under accepted ADR 0009; [operator walkthrough](../runbooks/event-recovery.md).

## Verified boundaries

Real PostgreSQL tests cover rollback before retry, persisted one/five-second retry times, three-attempt exhaustion, terminal invalid envelopes, stale failure reporting, operator replay races, original-byte retention, duplicate-effect prevention and safe downgrade rejection. Tests move persisted due times only where needed to avoid sleeping; assertions separately verify exact scheduled delays.

Separate Python processes are terminated after a claim, after an uncommitted effect, and after effect/receipt commit. A fresh CLI process recovers the first two after lease expiry. An explicit replay after commit finds the receipt and adds no second effect. Each case retains two attempts and exactly one database effect. Another test leaves the polling process alive across two separately published contexts. These exercise the recovery probe, not a city checkpoint or live provider.

Diagnostics tests ensure exception text and database passwords do not appear in persisted failure records or CLI output. Migration checks preserve existing work and refuse downgrade when it would erase retry/replay/probe data. No cleanup command deletes production delivery history.

Review regressions create a real two-transaction deadlock, raise PostgreSQL serialization failures, and terminate each test connection after a local effect. Recognized database failures roll back and retain infrastructure attempts without consuming the handler budget; successful retry writes once. Tests also cover delayed reconciliation, lost commit acknowledgement, idempotent refunds, stale fences, capped/resettable polling backoff and consecutive replay generations with audit links.

## Check results

- Ruff lint/format and mypy passed; frontend lint/format and production build passed.
- Unit/API suite: 380 passed.
- Real PostgreSQL/PostGIS integration suite: 98 passed, including 22 worker/recovery cases and the existing 25 ledger cases.
- Actual Compose smoke passed under `python -O`: cold readiness, migration/import, city/boundary/evidence, proxy, API recreation, repeated initialization, independent worker execution and replay, plus recovery by the same continuous worker after its isolated PostgreSQL container restarts. Its isolated stack and volume were removed afterward.
- Browser code is unchanged; this checkpoint verifies the UI production build and Compose proxy, with browser e2e also configured in CI.

## Remaining evidence

Location Intelligence checkpoint/timer wiring, city equivalence across expiry and producer crashes, measured large-history performance, and full city recovery walkthrough belong to the remaining EVENT-01 slices. Browser clocks continue to use isolated synchronous replay.

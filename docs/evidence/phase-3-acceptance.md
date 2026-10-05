# Phase 3: Durable event reliability acceptance

Date: 5 October 2026. Candidate based on merged `62c253ea049ed1514dc5119f0296a82bd4d7a65d`, with the city metrics command and container check in this change. Progress and release readiness are maintained in the [delivery plan](../delivery-plan.md).

## Acceptance map

The boundary is the accepted [ADR 0009](../adr/0009-durable-event-delivery.md) PostgreSQL outbox/consumer ledger and bounded synthetic city runs. The [Phase 3 specification](../architecture/event-01-durable-delivery.md) owns the detailed cases.

| Required behavior | Reproducible proof |
| --- | --- |
| Producer domain write and publication commit/rollback together | `test_domain_and_publication_roll_back_together` in [event store tests](../../tests/integration/test_event_store.py) |
| Competing workers, independent consumers and lease fencing | Unique concurrent claims, expired-claim rollback and independent consumer tests in [event store tests](../../tests/integration/test_event_store.py) |
| Duplicate, changed old identity and out-of-order revision handling | `test_duplicate_and_old_identity_conflict_precede_revision_ordering` in [event store tests](../../tests/integration/test_event_store.py); typed envelope tests retain trace/numeric equivalence |
| Consumer effect, receipt and derived publication stay atomic | `test_effect_receipt_and_derived_publication_roll_back_then_commit_once` in [event store tests](../../tests/integration/test_event_store.py) |
| Durable retry budget, invalid/conflicting envelopes and dead letters | [Recovery tests](../../tests/integration/test_event_recovery.py), including restart scheduling and terminal failure cases |
| Operator replay preserves identities, original bytes and audit generations | Worker replay and generation-link tests in [recovery tests](../../tests/integration/test_event_recovery.py) |
| Process death before/after commit cannot create duplicate effects | Separate-process termination tests in [recovery tests](../../tests/integration/test_event_recovery.py) and [city run tests](../../tests/integration/test_city_runs.py) |
| A blocked lane does not block independent work | [Ordered delivery tests](../../tests/integration/test_ordered_delivery.py) and bad-checkpoint isolation in [city review tests](../../tests/integration/test_city_run_review.py) |
| Every completed city checkpoint matches synchronous replay | All seven scenarios in `test_every_completed_checkpoint_matches_synchronous_city` in [city run tests](../../tests/integration/test_city_runs.py) |
| Warning expiry survives restart without a new weather capture | Persisted expiry test plus isolated [Compose walkthrough](../../scripts/compose_smoke.py) |
| GET/rewind neither publishes nor moves durable cursors | Read-only snapshot/run inspection test in [city run tests](../../tests/integration/test_city_runs.py) and browser replay checks |
| Versioned observation migration preserves imports and opaque fields | [Observation migration tests](../../tests/integration/test_observation_migration.py) and [storage evidence](event-01-observation-storage.md) |
| Database outage does not consume handler retries or stop polling permanently | Serialization/deadlock/reconciliation tests and isolated database restart in [Compose smoke](../../scripts/compose_smoke.py) |
| Operators can observe actual city input/result delivery state | [City metrics subprocess tests](../../tests/integration/test_city_metrics_operations.py): empty, pending, retry, dead-letter, replay and both consumers drained; CLI failure tests reject partial success |
| Performance changes preserve replay and rollback semantics | [Six-case benchmark](event-01-performance.md), [copy optimization comparison](event-01-planning-copy-cost.md) and nested-mutation failure tests |

## Run the acceptance checks

From the repository root, with Docker Desktop and local PostGIS available:

```powershell
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked pytest -q
uv run --locked pytest -q -m integration
python -O scripts/compose_smoke.py
```

The Compose check owns a uniquely named stack and volume; it builds the app, verifies initializer/readiness/proxy behavior, replays across workers, reconstructs city checkpoints across warning expiry, calls city metrics, restarts its database and cleans up its own stack. Provider keys and cloud resources are not used.

Local verification on 5 October 2026: Ruff lint/format and mypy passed; 409 unit/API tests and 140 PostGIS integration tests passed. The isolated Compose smoke also passed under `python -O`, including the city metrics command and database restart recovery, then removed its stack and volume. Browser code is unchanged; this local verification did not rerun Playwright. The candidate PR CI supplies the browser check before release.

## Demonstration

Use the [city checkpoint walkthrough](../runbooks/city-checkpoints.md) to create a bounded run, advance it, stop/restart the worker across warning expiry, inspect the completed snapshot and read both consumers' metrics. Use the [recovery runbook](../runbooks/event-recovery.md) for terminal-delivery inspection and explicit replay. The existing browser remains the independently rewindable synchronous reference; its slider does not control the durable worker.

Read-only inspection of the existing local retained fixture run reported 39 completed input deliveries and 9 completed result deliveries, with no queued retry, dead letter or backlog at this checkpoint. These are local demonstration counts, not fleet totals, live source freshness or production SLOs. Integration tests establish the blocked/recovery transitions in isolated schemas.

## Release and deferred boundaries

After this acceptance change is reviewed and merged, verify CI at the merged revision, then create the `phase-3` tag/release on that revision. Release notes must link the actual successful CI run, this evidence and the two operator walkthroughs. A candidate PR is not a released phase; no phase tag is created before approval.

[Issue #16](https://github.com/maxtsec/urban-pulse-au/issues/16) records repeated planning profile parsing and is deferred; it is not a Phase 3 exit gate. Live source authorization/retention (SRC-02), early collection (CLOUD-01), cloud deployment/telemetry (Phase 4), Phase 1 fixture-policy acceptance and earlier phase releases remain separate. This acceptance does not change their decisions or describe the synthetic city as live.

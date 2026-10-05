# Phase 3: Durable event reliability acceptance

Date: 5 October 2026. Integrated in [PR #17](https://github.com/maxtsec/urban-pulse-au/pull/17) at `a9359d0d1d9107413db4b4b6fc3cc42378537524`; [merged-commit CI](https://github.com/maxtsec/urban-pulse-au/actions/runs/37277546614) passed, including browser and Compose checks. Progress and release readiness are maintained in the [delivery plan](../delivery-plan.md).

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
| Operators can observe actual city input/result delivery state | [City metrics subprocess tests](../../tests/integration/test_city_metrics_operations.py): empty, pending, retry, dead-letter, replay and both consumers drained; CLI failure tests reject partial success; [blocked-lane tests](../../tests/integration/test_blocked_metrics.py) cover transitive dependencies, independent lanes/consumers and replay across completed successors |
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

Local verification on 5 October 2026: Ruff lint/format and mypy passed; 409 unit/API tests and 142 PostGIS integration tests passed. The initial city-metrics revision also passed isolated Compose smoke under `python -O`, including the city metrics command and database restart recovery, then removed its stack and volume. Browser code is unchanged; this local verification did not rerun Playwright. The linked main-branch CI also passed browser and Compose checks on the exact merged commit above. Production release requires CI at its selected commit.

## Demonstration

Use the [city checkpoint walkthrough](../runbooks/city-checkpoints.md) to create a bounded run, advance it, stop/restart the worker across warning expiry, inspect the completed snapshot and read both consumers' metrics. Use the [recovery runbook](../runbooks/event-recovery.md) for terminal-delivery inspection and explicit replay. The existing browser remains the independently rewindable synchronous reference; its slider does not control the durable worker.

Read-only inspection of the existing local retained fixture run reported 39 completed input deliveries and 9 completed result deliveries, with no queued retry, dead letter or backlog at this checkpoint. These are local demonstration counts, not fleet totals, live source freshness or production SLOs. Integration tests establish the blocked/recovery transitions in isolated schemas.

## Release and deferred boundaries

Phase 3 is recorded by its merged commit, CI, demonstrations and this evidence. It does not require a phase tag or earlier phase releases. Follow the [production V1 release policy](../delivery-plan.md#release-policy) for `v1.0.0`; outstanding policy decisions and the complete city release criteria still apply before production.

[Issue #16](https://github.com/maxtsec/urban-pulse-au/issues/16) records repeated planning profile parsing and is deferred; it is not a Phase 3 exit gate. Live source authorization/retention (SRC-02), early collection (CLOUD-01), cloud deployment/telemetry (Phase 4) remain separately scoped. This acceptance does not change their decisions or describe the synthetic city as live.

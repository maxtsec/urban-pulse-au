# Durable worker recovery

Decision: [ADR 0009](../adr/0009-durable-event-delivery.md). Progress: [delivery plan](../delivery-plan.md). Evidence: [worker recovery checks](../evidence/event-01-worker-recovery.md).

## Scope and upgrade

The local CLI runs the explicitly registered `recovery-probe-v1` consumer. Its synthetic database effect proves the worker/transaction boundary; it is not the Location Intelligence projection. Existing city imports and browser requests enqueue nothing. The application worker accepts an injected handler; the independent [city worker](city-checkpoints.md) binds Location Intelligence and persisted timer checkpoints.

Stop old delivery processes and run `uv run --locked python -m urbanpulse.adapters.city_store migrate` before using this worker. Migration `0006_worker_recovery` preserves existing publications, deliveries and attempts, adds `available_at`, permits retry state, and creates replay audit and synthetic-effect tables. Existing pending work is immediately eligible. The API remains usable without a worker.

Downgrade to `0005` refuses to discard scheduled retries, replay audit or probe effects. It rolls back without changing the database when these exist. Do not delete history to force a downgrade; retain the compatible schema and roll forward with a fix.

## Local walkthrough

Start the local PostgreSQL service, apply migrations, then use a fresh context for each demonstration:

```powershell
uv run --locked python -m workers.events.main seed-probe --context demo-recovery-01
uv run --locked python -m workers.events.main run --once
uv run --locked python -m workers.events.main list --context demo-recovery-01
```

The first worker invocation reports `apply`. Copy the delivery ID and generation from the result into these commands:

```powershell
uv run --locked python -m workers.events.main inspect <delivery-id>
uv run --locked python -m workers.events.main replay <delivery-id> --generation <generation> --reason verify-deduplication
uv run --locked python -m workers.events.main run --once
uv run --locked python -m workers.events.main metrics
```

Replay reports `duplicate`, with one committed probe effect and both attempts retained. Repeating `seed-probe` for the same context returns its original publication and does not requeue completed work. Use `run` without `--once` for continuous polling; Ctrl+C stops after the current step. Idle polling waits outside database transactions. The worker claims one delivery at a time, so a locally queued batch cannot expire while waiting for its turn.

`--once` performs one claim sweep, not a drain or an assertion that a context is complete. It can report `idle` while retries are not due, deliveries are leased/locked, or a sweep has just scheduled an expired claim. Check `inspect`/`metrics`, or leave the worker running.

## Retry and dead letters

The fixture policy permits three charged attempts per initial delivery or explicit replay cycle. Claiming reserves one charge; a recognized database transaction failure refunds that charge after rollback/reconciliation, while retaining the physical attempt as `infrastructure-error`. Handler failures and unreported lease expiries retain their charges. Handler failures roll back effects, receipts and derived publications before a separate fenced transaction records a safe category and a next-attempt time. The delays are one second after attempt one and five seconds after attempt two. PostgreSQL time owns scheduling. A replaced or expired claim cannot record failure against a new worker's attempt.

Lease expiry also consumes an attempt. A claim sweep records `lease-expired` and schedules from the expired deadline plus the same delay; if that time has already passed, it can reclaim immediately. The third expired attempt becomes `attempts-exhausted`. Invalid stored envelopes and publication conflicts are terminal immediately. Arbitrary handler exceptions, including ordinary `ValueError`, use the bounded retry policy. Raw exceptions, SQL parameters and payloads are not diagnostic fields.

The PostgreSQL adapter translates DBAPI errors (including deadlocks, serialization failures and disconnects) and connection-pool timeouts into an application storage failure. The worker records no handler failure for these. It reconciles the claim under its original fence, refunds the charge once, and schedules an infrastructure retry. If the database is still unavailable, the running worker retains that claim and retries reconciliation before claiming more work. An expired but unreplaced claim can be reconciled. A replaced generation is left untouched; a commit whose acknowledgement was lost keeps its stored outcome and charge.

This distinction requires the worker to report the storage failure. A process killed before it can report, or a lease already reclaimed by another worker, remains an unreported lease expiry under ADR 0009. Its attempt is not retrospectively rewritten or refunded. Inspection distinguishes physical attempt history from `attempt_count`, the charged attempts in the current replay cycle.

Inspect a dead letter, resolve the cause, then replay with the inspected generation and one required reason: `operator-retry`, `handler-fixed`, or `verify-deduplication`. Replay accepts only complete/dead-letter deliveries; it cannot steal leased or scheduled work. It resets the cycle's attempt count, reserves the next fencing generation, and records the reason/time atomically. The first claim uses that reserved generation; subsequent retries advance it. Each inspected attempt includes `replay_generation` (null for the initial cycle), so an existing history with older gaps can also be traced without rewriting records. Previous attempts, receipts, original event identity and wire bytes remain unchanged. A second operator holding the old generation is rejected. A corrected payload requires a new domain revision, not replay or history editing.

The CLI returns JSON and a nonzero exit code for database/schema failures (2), stale/nonterminal replay (3), and invalid/unknown requests (4). One-shot and inspection commands exit on database failure. Continuous polling stays alive and waits 1, 2, 4, 8, 16, then at most 30 seconds between database retries; a successful step resets the delay. The wait responds to stop signals. Committed work remains discoverable, and a claim left leased after a process crash is recovered after expiry. No HTTP failure-injection or replay endpoint is exposed.

## Inspection and Compose

`inspect` returns one consistent view of the delivery, attempts and replay reasons, without the envelope. `list` returns at most 100 oldest deliveries in a context; inspect a known ID directly if outside that bounded listing. `metrics` reports current status counts, retry/dead-letter counts, backlog count and the age of its oldest original delivery. It uses the registered consumer as its only dimension; event IDs appear only in inspection, not metric labels. Manual replay retains original delivery age.

The `recovery` profile is opt-in and shares the API image. From a migrated app installation:

```powershell
docker compose --profile app up -d --build --wait
docker compose --profile recovery run --rm --no-deps recovery-worker /app/.venv/bin/python -m workers.events.main seed-probe --context compose-recovery-01
docker compose --profile recovery up -d recovery-worker
docker compose logs recovery-worker
docker compose stop recovery-worker
```

A standalone recovery profile does not migrate automatically: apply migrations first using the API image or local migration command. Continuous workers resume automatically after database/schema recovery. Compose uses `restart: on-failure` as a fallback if the process exits unexpectedly; an explicit stop remains a stop. The Compose smoke test seeds the probe, executes it in a separate container, replays it in another container, and verifies the city response is unchanged. It also stops and starts its isolated PostgreSQL container, observes the outage, and verifies the same worker incarnation processes a newly published event afterward. Process-kill regression seams exist only under `tests/helpers`.

City-run delivery IDs use the same list/inspect/replay commands. The independent `city-worker` processes their registered consumers; follow the [city checkpoint walkthrough](city-checkpoints.md) for run clocks and completion barriers.

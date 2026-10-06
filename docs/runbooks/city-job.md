# Finite fixture worker Job

Scope: the manually triggered worker selected in [ADR 0012](../adr/0012-managed-demo-resource-profile.md). Progress: [delivery plan](../delivery-plan.md). This runner uses already migrated, imported inputs and the restricted worker SQL login; it does not initialize roles, migrate or import data.

## Invocation and completion

Supply `DATABASE_URL` privately from the worker's numbered secret version. Use the verified import ID emitted by fixture initialization, a stable run ID and an explicit target within 0–360 seconds:

```sh
uv run python -m workers.city.job demo-city --scope IMPORT_ID --scenario city --seconds 360 --timeout-seconds 540
```

Replace `IMPORT_ID` with the 64-character import hash. Do not put credentials in arguments. In the application image use `/app/.venv/bin/python -m workers.city.job` with the same arguments. The future Cloud Run Job must use this finite entrypoint, one task, parallelism one, retries zero and a 600-second task timeout. Do not deploy the continuous `workers.city.main run` command or interpret its `--once` sweep as completion.

The runner creates or validates the pinned run/scope/scenario, advances to the target, and drains only that run's two registered consumer lanes. Exit zero requires the target checkpoint/result, every scheduled checkpoint and every registered input/result delivery to be complete. A completed checkpoint with a pending or failed result delivery is insufficient. Repeating the same completed request does not add effects; rewinding or changing the pinned scope/scenario fails. Advancing a healthy run to a later target is supported.

The final JSON contains only a status, validated run ID and target. `complete` exits zero; `busy`, `session-lost`, `database-unavailable`, `checkpoint-error`, `dead-letter`, `deadline-exceeded`, `interrupted`, invalid arguments/inputs/configuration and unexpected execution failure exit nonzero. Treat process failure without a completion record as failure. Job submission alone never permits deployment promotion.

## Execution lock and resource bounds

The runner takes database-wide session advisory lock `(850601, 1)` before application work. It uses a single physical session for the lock, input reads, spatial checks and event/checkpoint writes. Pool size is one with zero overflow and a one-second checkout wait, within the accepted worker role cap of four. Query timeout is ten seconds, lock wait three seconds, and spatial statements retain their three-second local timeout.

A second lock-aware mutation Job fails promptly as `busy`. Transactions may commit while the session lock remains held. If the physical connection is lost, the runner refuses replacement connections and exits; it cannot reconnect and continue writes without its original lock. Closing the child/session releases the lock. This requires session-preserving connectivity, such as the selected managed Cloud SQL connector; transaction-pooling middleware is unsupported. [PostgreSQL advisory-lock behavior](https://www.postgresql.org/docs/17/explicit-locking.html#ADVISORY-LOCKS).

[Migration/import Jobs](initialization-jobs.md) join this same mutation lane and use the same finite supervisor. Existing development CLIs and continuous workers do not participate in it: stop them before this runner is used against that database. Do not claim global serialization while a legacy writer is still enabled. No migration, new grants or additional database role is introduced by this runner.

## Deadline, cancellation and recovery

The outer process starts a dedicated child and owns a wall-clock deadline covering its startup and work. The default/maximum is 540 seconds, leaving room inside the 600-second Cloud Run task limit. Smaller positive integer limits are supported. Deadline expiry or SIGTERM/SIGINT stops the child, escalates termination after five seconds if needed, and waits for cleanup; SQL blocking or CPU work cannot rely solely on the next polling iteration to stop. The outer supervisor opens no database session.

Only committed checkpoints/receipts survive interruption. Rerun the same pinned request after checking the failure; outstanding delivery leases may need to expire before processing resumes. A lost database connection fails this invocation rather than retrying through an unguarded new session. Recorded checkpoint errors and dead letters require the existing [recovery procedure](event-recovery.md) / [checkpoint controls](city-checkpoints.md); rerunning or requesting a later target does not silently clear them. Never delete retained history to force success.

Before creating a managed Job, verify its actual command, timeout, retries, secret version and identity; measure connections during cancellation/overlap; confirm logs and nonzero exit behavior; and record a successful terminal result. Local [acceptance evidence](../evidence/demo-01-city-job.md) does not establish managed Job/IAM integration.

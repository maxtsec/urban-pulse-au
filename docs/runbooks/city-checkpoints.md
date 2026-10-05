# Durable city checkpoint walkthrough

Decision: [ADR 0009](../adr/0009-durable-event-delivery.md). Progress: [delivery plan](../delivery-plan.md). [Verification evidence](../evidence/event-01-city-checkpoints.md).

## Run a retained fixture

Start the local database and prepare the import using the [quickstart](../../README.md#fixture-quickstart). Apply migration `0007_city_checkpoints` before starting either event worker:

```powershell
uv run --locked python -m urbanpulse.adapters.city_store migrate
uv run --locked python -m workers.ingestion.main --city-fixture
uv run --locked python -m workers.city.main create southbank-demo --scenario city
uv run --locked python -m workers.city.main advance southbank-demo --seconds 360
uv run --locked python -m workers.city.main run
```

In another terminal:

```powershell
uv run --locked python -m workers.city.main inspect southbank-demo
uv run --locked python -m workers.city.main inspect southbank-demo --seconds 60
uv run --locked python -m workers.events.main list --context city-run:southbank-demo
```

The first command pins the active immutable import. Use `create ... --scope <import-id>` to choose another retained import explicitly. Repeating creation with the same identity is safe; a different scope or scenario needs a new run ID. `advance` accepts an integer from 0 to 360, including the current target, and refuses rewind. `run --once` performs one worker step; it does not drain a whole run. Stop the continuous worker with Ctrl+C.

For Docker, first run `docker compose --profile app up -d --build --wait`. Create and advance through `docker compose run --rm --no-deps city-worker /app/.venv/bin/python -m workers.city.main <command>`. Then start `docker compose --profile city-recovery up -d city-worker`. The worker uses the shared API image and database, with `restart: on-failure`; it needs no shared raw-file volume. Stop it with `docker compose stop city-worker`. Apply migrations before upgrading running workers.

## Read the result

- `target` is the explicitly requested fixture clock; `completed` is the latest atomically completed checkpoint, initially -1.
- `scheduled` checkpoints have retained manifests but have not published their inputs. Only the earliest incomplete checkpoint can become `pending`.
- `pending` means input delivery or reconstruction is outstanding. `blocked_publications` lists dead letters; `error` reports a sanitized checkpoint validation, reconstruction or publication failure.
- `complete` means every required input was delivered and the snapshot, run cursor and any derived area event committed together. Without an explicit clock, `snapshot` is the last completed result; its own clock must be read alongside `target`. Requesting an incomplete or absent checkpoint returns a null snapshot.

Location Intelligence consumes `city-location-v1` envelopes into its own durable inbox, with the generic receipt in the same transaction. Reconstruction uses those admitted envelopes plus pinned source history and capture/coverage evidence. Missing or changed delivered input prevents completion. Rejected and superseded source attempts stay in the import for replay diagnostics; they are not promoted into authoritative outbox inputs.

The coordinator loads and verifies inputs, runs PostGIS checks and rebuilds the projection before acquiring the run lock. Under the lock it rechecks the run identity/cursor, checkpoint, delivery readiness and delivered envelopes. Concurrent advancement or completion discards the prepared result; a later poll starts from the new state. It saves the completed snapshot, semantic transition history, derived `AreaStatusChanged` publication and next checkpoint's publication intent in one transaction. The separate `city-results-v1` consumer records derived events for inspection. Checkpoint completion guarantees that result publication is durable; downstream result delivery can still be pending. Area-event identity remains identical to synchronous replay, scoped by run only in the delivery ledger.

The producer prepares only missing checkpoints after the completed clock, reusing existing pending manifests. Publication ordering retains only the last publication ID: the queue adapter reports whether an envelope was newly created, so a duplicate cannot move that cursor backwards. Each checkpoint still retains its own required delivery references.

Both input and result deliveries have per-consumer predecessor dependencies. A pending, leased or dead-lettered predecessor prevents claiming its successor without consuming retry attempts. Other consumers and runs continue. This is ordered delivery within an explicit lane, not global queue ordering.

## Monitor both city consumers

```powershell
uv run --locked python -m workers.city.main metrics
```

For the container installation:

```powershell
docker compose run --rm --no-deps city-worker /app/.venv/bin/python -m workers.city.main metrics
```

The read-only command returns `consumers`, containing `city-location-v1` (domain inputs) and `city-results-v1` (derived area events). It requires the queue schema but no active fixture import, run or spatial reconstruction. Database/schema failure returns exit code 2 and a sanitized error, never a partial or all-zero success report.

Each consumer uses the existing queue metric definitions:

| Field | Interpretation |
| --- | --- |
| `counts` | Current delivery counts by status; absent statuses have zero deliveries |
| `backlog_count` | Pending, leased and retry deliveries across all runs for this consumer |
| `backlog_age_seconds` | Age of the oldest original delivery still in that backlog; zero when empty; replay retains original age |
| `retry_count` | Deliveries currently waiting in retry, not cumulative attempts |
| `dead_letter_count` | Deliveries currently dead-lettered; inspect/replay using the existing operator commands |

These are separate consumer reads, not one atomic cross-consumer snapshot. No run/event IDs become metric dimensions. Zero backlog does not mean a run is complete: dead letters are reported separately, and future scheduled checkpoints have not yet published deliveries. Check `inspect <run-id>` for checkpoint errors, blocked publications, target and completed clocks. Result delivery may lag an already completed checkpoint.

## Restart across warning expiry

Create a fresh run with `--scenario weather-outage`, advance to 239 and let it complete. Stop the worker, advance to 240, then recreate/start the worker. The persisted timer checkpoint changes Degraded to Unknown after the warning expires, even though no new weather capture arrives. Unknown remains explainable through missing current coverage.

`advance` persists all due source and validity/freshness boundaries up to the requested target. Workers process these stored checkpoints after restart. The clock is a bounded fixture clock controlled by the operator; the command does not schedule a wall-clock live collector. Source history is pinned, and no frame after a checkpoint is admitted into its result.

Browser GETs and the slider still run independent synchronous replay. Reading 360 then 0 neither publishes events nor moves these durable runs. This allows comparing both delivery paths without changing the public city API.

## Recover a blocked run

Use `workers.events.main list --context city-run:<run-id>` and `inspect <delivery-id>` to find the consumer, terminal status and latest generation. Follow the [replay procedure](event-recovery.md) with that exact delivery ID/generation and an allowed reason. The city worker resumes its dependent checkpoints after successful delivery. Original bytes, event identities and attempts remain intact; an already applied event does not create a second inbox effect.

Checkpoint validation/missing-input failures report `checkpoint-reconstruction-unavailable`; publication conflicts report `checkpoint-publication-conflict`. The failed transaction rolls back before a separate, fenced transaction records the error on that checkpoint. A stale failure report cannot mark a checkpoint after another worker or producer has advanced the run. Other runs continue without restarting the process. Resolve the underlying input, version or producer discrepancy first. Repeating `advance` at the current target re-arms incomplete checkpoints for evaluation; it does not rewrite pinned identity or restore missing inbox data. Do not edit immutable envelopes to bypass validation. Use a new run for intentionally changed inputs or policy versions.

Database failures use the shared worker backoff/reconciliation policy; they do not consume handler retries. The coordinator rolls back its transaction and retries after reconnection. API readiness does not depend on a completed durable run.

## Migration and limits

Migration `0007` adds three Location Intelligence tables and nullable per-delivery predecessor references. Existing unordered deliveries and imports remain usable. Run ordering stores only the input/result publication cursors; required publication references belong to each checkpoint. It enqueues no work and changes no active import. Downgrade refuses any retained city run or ordered dependency history; this walkthrough has no destructive cleanup command.

The first verified local run is `event01-city-checkpoints-01`; the commands above create a separate `southbank-demo` run. Both remain in PostgreSQL until an explicitly scoped lifecycle operation is designed. A new run duplicates bounded replay history and results. Reconstruction reloads and validates inputs and retains candidate-state copying; large-history timings and any cache/copy optimization remain a separate measured change.

Run `uv run --locked pytest tests/integration/test_city_runs.py tests/integration/test_ordered_delivery.py tests/integration/test_city_run_review.py -m integration -q` for the real database checks. `python -O scripts/compose_smoke.py` builds an isolated stack, compares durable city results with the API, recreates its worker across expiry and removes only its generated test stack/volume.

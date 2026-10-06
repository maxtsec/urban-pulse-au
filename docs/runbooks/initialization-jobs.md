# Finite migration and fixture import Jobs

Decision: [ADR 0010](../adr/0010-hosted-fixture-demo.md) and [ADR 0012](../adr/0012-managed-demo-resource-profile.md). Progress: [delivery plan](../delivery-plan.md). These explicit entrypoints prepare the schema and synthetic inputs before serving promotion. They never run from API startup.

## Prerequisites and commands

Complete the [private database bootstrap](demo-database.md) first: PostGIS, four restricted SQL logins and their numbered secret versions must already exist. These Jobs do not create roles, install extensions, rotate credentials or change cloud resources. Stop legacy migration/import commands and continuous workers before running against the same database; those development entrypoints do not acquire the deployment lock.

Use the reviewed application image digest for both operations. Inject `DATABASE_URL` privately from the matching migration/import secret, with its matching service identity. Never put credentials in command arguments or logs. In the image run:

```sh
/app/.venv/bin/python -m workers.initialization.job migrate --database urbanpulse --expected-revision 0007_city_checkpoints --timeout-seconds 540
/app/.venv/bin/python -m workers.initialization.job import --database urbanpulse --expected-revision 0007_city_checkpoints --timeout-seconds 540
```

Locally replace `/app/.venv/bin/python` with `uv run python`. `--role-prefix` defaults to `urbanpulse`; use a different prefix only for an explicitly provisioned target. The runner checks the actual database name, SQL login, image migration head and reviewed revision. The import login must find that exact revision already installed. Optional `--expected-import-id HASH` pins an import to a previously verified 64-character identity; the runner derives this identity from the verified capture and normalizer version before normalization or persistence. Mismatches fail without storing import history or changing the active selection.

Future managed Job resources must configure one task, parallelism one, retries zero and a 600-second task timeout. The shared supervisor allows at most 540 seconds, including child startup, with bounded termination cleanup. A successful child result read just after the deadline remains successful; absent a normal exit/result, deadline expiry fails. SIGTERM/SIGINT cancels the owned child. A submission or task creation is not proof of completion.

## Serialization and transactions

Migration, import and the [finite worker](city-job.md) share database-wide session advisory lock `(850601, 1)`. Every SQL operation uses the same physical session, with pool size one and zero overflow. A concurrent Job returns `busy`; a lost connection cannot reconnect and continue writing without its original lock. The supervisor itself opens no SQL session. These runners fit within the existing migration/import/worker role caps; the conservative deployment connection envelope is unchanged.

Migration configures private default privileges, applies the image's reviewed migrations, refreshes the closed grant matrix and verifies the revision in **one caller-owned transaction**. Failure rolls back that transaction. This relies on the current seven transactional migrations; adding autocommit or nontransactional operations requires a separate design review and recovery procedure. Update `EXPECTED_REVISION` and the access matrix in `urbanpulse/adapters/demo_database.py` with every new migration, following the [migration checklist](demo-database.md#migration-checklist). The operator helper at `scripts/demo_database.py` remains a compatibility import for private bootstrap tooling.

Import captures the image's synthetic fixtures in a temporary directory, normalizes them through PostGIS and saves immutable history without selecting it. It verifies the persisted history before atomically selecting the import. Failure before selection keeps the previous active pointer; a failed attempt may leave unselected immutable history. Do not delete it to force a retry. A process can fail after selection commits but before reporting completion: inspect the active pointer and rerun the same image/pin to verify completion. Repeating the same import does not duplicate history. Normal exit removes temporary capture files; forced termination may leave the invocation's local temporary directory until container removal or operator cleanup. PostgreSQL retains the normalized inputs and evidence used by the API.

## Results and recovery

For valid requests, the final JSON contains `operation`, `status`, and on success `schema_revision`; successful imports also return `import_id`. Record those values with the image digest and Job execution ID, then use that import ID for the worker. `complete` exits zero. Busy, invalid arguments/inputs/configuration, unavailable database, session loss, interruption, deadline expiry and unexpected failures exit nonzero with redacted diagnostics.

On failure, inspect the schema revision, active import and execution state privately. Release the conflicting Job or restore database connectivity, then repeat the same pinned operation. Never automatically downgrade migrations, rotate secrets, broaden grants or remove retained data. Before promotion, require successful migration/import results, read-only API readiness and city checks, the bounded worker result when invoked, and the separate restore/managed connectivity gates in the [resource plan](../architecture/demo-cloud-resource-plan.md).

Local [acceptance evidence](../evidence/demo-01-initialization-jobs.md) exercises real restricted logins and child processes. Actual Cloud Run identity, secret/socket wiring, task limits and managed recovery must be verified at deployment.

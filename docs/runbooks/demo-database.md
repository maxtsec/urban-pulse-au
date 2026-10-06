# Private demo database initialization

Scope: the accepted roles and connection envelope in [ADR 0012](../adr/0012-managed-demo-resource-profile.md) and the [resource plan](../architecture/demo-cloud-resource-plan.md). Progress is maintained in the [delivery plan](../delivery-plan.md). This procedure follows the reviewed foundation apply.

## Privilege matrix

`scripts/demo_database.py` is an explicit operator helper, never an API startup hook. It creates four login roles with no superuser, database/role creation, replication, RLS bypass, inherited membership or grant option. Only the migration role can create objects in `public`; it does not own the database or PostGIS extension.

| SQL role | Connection cap | Access |
| --- | ---: | --- |
| `urbanpulse_runtime` | 12 | Read the eight `city04_*` input/pointer tables and migration version; execute public PostGIS functions |
| `urbanpulse_import` | 3 | Read/insert those inputs; update only `city04_active_imports`; no history rewrite/delete or event writes |
| `urbanpulse_worker` | 4 | Read inputs/version; select/insert ten `event01_*` tables; update deliveries, attempts, cursors, runs and checkpoints; no input writes |
| `urbanpulse_migrate` | 2 | Own application tables and DDL; set their grants and private defaults |

No application role can become another role. Runtime/import/worker receive no delete, truncate, create or temporary-table privilege in the application database. Schema ownership and PostGIS remain with the bootstrap operator/platform. This is a grant matrix for the application database, not a claim about other databases' default `CONNECT` privileges.

The helper checks the explicit target database, fresh role names and empty public application tables before bootstrap. It requires caller-owned transactions. Re-running bootstrap/activation refuses existing roles rather than adopting them or silently rotating credentials. `grant_access` checks the exact table set, migration ownership and revision `0007_city_checkpoints` before applying its allowlist; it can be repeated for that revision. A migration adding/renaming tables requires an access-matrix review.

New migration-owned tables, sequences, functions and types have no `PUBLIC` grant. No automatic future application grants are installed. Function defaults are revoked globally: a schema-local revoke cannot remove global `PUBLIC EXECUTE`. PostGIS functions are installed by the operator before these migration defaults and remain callable. [PostgreSQL default privileges](https://www.postgresql.org/docs/17/sql-alterdefaultprivileges.html).

## Operator sequence

1. Confirm the project/instance/database and completed foundation apply; review current users, empty secret containers and schema before any mutation. Use the Cloud SQL Auth Proxy on loopback with operator application-default credentials. Verify the downloaded executable against its official release checksum. Close only the proxy process started for this operation when finished.
2. Initialize the default operator password only on the new instance. Generate distinct random application credentials and keep a recoverable encrypted private copy before database changes. Never put passwords in arguments, shell history, Terraform, Git, stdout or test reports. Windows operator recovery may use user-bound DPAPI; it requires the same Windows user/profile and machine and is not a portable disaster-recovery backup. Plan password reset/rotation through the authorized operator identity if it becomes unavailable.
3. In a transaction as the bootstrap operator, call `bootstrap(connection, database="urbanpulse")`, then `activate_roles(connection, passwords, database="urbanpulse")`. The password mapping has `runtime`, `migrate`, `import`, `worker` keys. Activation sends SCRAM verifiers rather than clear-text passwords in SQL statements. The module does not generate, persist or publish secret values.
4. Connect as `urbanpulse_migrate`, call `configure_defaults` in a transaction, run the existing seven Alembic migrations explicitly, then call `grant_access` in a transaction. Serialize this private one-off operation; do not invoke it from API startup. The future deployed migration Job still needs its own bounded lock/runner.
5. Read back role attributes/memberships, ownership, `PostGIS_Full_Version()`, migration revision, `max_connections`, both reserved settings and baseline client connections. Test actual permitted operations, denied cross-role writes, and one extra connection beyond every role cap. Release all test sessions afterwards.
6. Publish a numbered version to each already-created matching secret container after its role authenticates. Use a `postgresql://` URL with that SQL username/password, database `urbanpulse`, and the managed socket path `/cloudsql/PROJECT:REGION:INSTANCE` as the URL-encoded `host` query parameter. Do not grant the application access to the operator credential. Read back and privately compare each stored payload; record version identifiers only. Serving/Jobs must reference those numbered versions.
7. Run the existing read-only Southbank/transport, weather and planning spatial tests through the runtime role against managed PostGIS. Do not run the whole destructive integration suite against the managed database. Record sanitized evidence and stop the temporary proxy.

For a partial failure, retain the encrypted recovery file and phase record, inspect actual roles/schema/secret versions, and resume only the unfinished phase. Do not blindly rerun bootstrap, reset working passwords, append secret versions or downgrade migrations. Credential rotation and revocation need a separately reviewed sequence.

Cloud SQL API-created built-in users receive administrative membership by default unless custom roles are selected. Application roles here are created through SQL and verified without that membership. [Cloud SQL users](https://docs.cloud.google.com/sql/docs/postgres/create-manage-users), [Auth Proxy](https://docs.cloud.google.com/sql/docs/postgres/connect-auth-proxy).

## Migration checklist

Every schema revision, including a data-only migration, must review the database permission gate before deployment:

1. Update the accepted revision in `scripts/demo_database.py:grant_access` alongside the migration. It deliberately refuses any revision other than `0007_city_checkpoints` today; do not bypass the check or infer grants from every discovered table.
2. Review the explicit input/event table sets, mutable-table allowlist, ownership and privilege matrix. Decide any new table, sequence, function or type privileges explicitly; private defaults grant nothing to application roles. Preserve cross-context write restrictions.
3. Run migration and access refresh as the migration login on a disposable database, then run `tests/integration/test_demo_database.py`. Its real CLI/API flow covers migration, repeated import, durable replay and runtime reads with separate logins, alongside negative privilege and connection-cap tests. Include upgrade/compatibility tests for the migration itself.
4. Before a managed upgrade, review the saved deployment/migration plan and backup/restore path. Serialize migration, apply the reviewed revision, refresh grants in a transaction and verify the real entrypoints. Do not rerun bootstrap or rotate credentials to refresh grants; an unexpected revision/table set must stop deployment.

## Verification and remaining deployment gates

`uv run pytest -m integration -q tests/integration/test_demo_database.py` creates a random database and role prefix on the configured local integration server, exercises real authentication/privileges/caps, and removes only those generated resources. The integration operator needs database/role creation rights; ordinary application accounts do not. Use `URBANPULSE_TEST_DATABASE_URL` only for an isolated development server.

Initialization does not import fixtures, run workers, create Cloud Run services/Jobs, grant IAP access, prove IAM service-identity authentication, or exercise restore. Shared API pooling, bounded Job runners/locks, actual serving overlap/saturation, fixture import and a restore rehearsal remain separate deployment gates. See the [dated evidence](../evidence/demo-01-database-bootstrap.md).

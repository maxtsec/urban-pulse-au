# DEMO-01 initialization Job acceptance

Verified: 6 October 2026 (Australia/Sydney). Procedure: [initialization Jobs](../runbooks/initialization-jobs.md). Decisions: [ADR 0010](../adr/0010-hosted-fixture-demo.md), [ADR 0012](../adr/0012-managed-demo-resource-profile.md). Progress: [delivery plan](../delivery-plan.md).

Validation passed: **520 unit tests**, **180 PostGIS integration tests**, Ruff lint/format, strict mypy over **61 source files**, and **603 relative documentation links**. The 11 initialization cases were rerun from roles/PostGIS only after removing prerequisite default-grant setup from the test helper. Real Compose smoke passed under `python -O`, including shared-supervisor worker execution and isolated resource cleanup. Separately, the built Linux application image completed migration, import and a worker target of 360 using the corresponding restricted logins; migration/import were also repeated from a fresh roles/PostGIS-only database.

The integration module `tests/integration/test_initialization_jobs.py` runs the actual finite CLI in child processes against disposable PostGIS databases with independently generated migration/import/worker/runtime SQL logins. It starts from PostGIS and roles only, so all seven migrations and grants are exercised through the new entrypoint.

| Case | Observed result |
| --- | --- |
| Initial migration and repeat | Reviewed schema/grants install using the migration login; repeating succeeds |
| Import and repeat | Import login produces one immutable import; a pinned repeat returns the same ID; runtime can read verified inputs and readiness while writes remain denied |
| Incorrect identity | Wrong database, SQL role or revision exits nonzero |
| Shared mutation lane | Migration and import both refuse while a worker session holds the lock |
| Grant failure | Unexpected table stops grant refresh and rolls back all seven migrations; removing the test obstacle permits retry |
| Import identity mismatch | Incorrect requested hash fails without changing the active pointer |
| Hard deadline | A blocked real SQL read is terminated; active selection is preserved and a later invocation succeeds |
| Invalid staged history | Corrupted unselected history fails verification and cannot replace the active import |

The existing worker regression tests continue to cover deadline/result precedence, cancellation, session loss, context isolation and full durable replay after extracting the common supervisor. The SQL privilege policy now lives in the application adapter packaged in the image; the operator helper preserves its import interface.

Reproduce with `uv run pytest -m integration -q tests/integration/test_initialization_jobs.py`, using `URBANPULSE_TEST_DATABASE_URL` for an isolated local PostGIS server. Test credentials are ephemeral; no cloud credentials are required. Actual Cloud Run resources/execution, managed secret/socket wiring, restore and deployment promotion are separate acceptance gates.

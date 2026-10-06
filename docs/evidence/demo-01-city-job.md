# DEMO-01 finite worker acceptance

Verified: 6 October 2026 (Australia/Sydney). Procedure: [finite worker runbook](../runbooks/city-job.md). Decision: [ADR 0012](../adr/0012-managed-demo-resource-profile.md). Progress: [delivery plan](../delivery-plan.md).

Validation passed: **506 unit tests**, **169 integration tests**, Ruff lint/format, strict mypy over **59 source files** and **581 relative documentation links**. Real Compose smoke passed under `python -O`, including the finite worker in the built Linux image, successful exit and parity with the API at second 360. Existing initialization, recreation, checkpoint expiry, database restart and optional-cache recovery also passed; generated containers/networks/volumes were removed.

The integration module `tests/integration/test_city_job.py` provisions a disposable database with four real restricted logins, migrates/imports through their entrypoints, and invokes the finite worker as a real child process using the worker role.

| Case | Required observation |
| --- | --- |
| Full target and isolation | The city reaches second 360 and matches read-only API composition; another pending run receives no claims or checkpoint progress |
| Repeat | Repeating the completed invocation adds no delivery attempts/effects |
| Connections | Sampled ordinary worker execution uses one tagged database session |
| Overlap | A held execution lock rejects another Job before it creates a run; release allows a later invocation |
| Lost session | Terminating the locked session prevents reconnection and subsequent writes |
| Hard deadline | A real blocked SQL operation is stopped by the supervisor deadline; a later invocation can complete |
| Cancellation | Cancellation stops the child and releases the execution lock for a later invocation |
| Terminal failures | Dead letters, checkpoint errors and missing registered deliveries prevent successful completion, including when requesting a later target |
| Result lane | A completed target checkpoint cannot hide a failed result delivery |

Unit checks reject invalid run/scope/scenario/target/deadline values before work, avoid spawning already-cancelled work, and emit only a redacted status for invalid configuration.

Reproduce against an isolated local PostGIS server with `uv run pytest -m integration -q tests/integration/test_city_job.py`. These tests use no cloud credentials. Migration/import Job wrappers, actual Cloud Run Job limits/identity/secret wiring, managed interruption measurements and promotion gates remain separate work; no cloud execution was performed here.

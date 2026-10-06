# DEMO-01 bounded API database pool

Verified: 6 October 2026 (Australia/Sydney). Decision: [ADR 0012](../adr/0012-managed-demo-resource-profile.md). Deployment envelope: [resource plan](../architecture/demo-cloud-resource-plan.md#connection-envelope). Progress: [delivery plan](../delivery-plan.md).

## Behavior

Each API lifespan owns one SQLAlchemy pool: size **2**, overflow **0**, checkout wait **1 second**, connection establishment timeout **3 seconds**, with pre-ping before reuse. Input reads, spatial membership/overlap and readiness share it. PostGIS and readiness queries use a transaction-local three-second statement timeout. No database connection is opened merely by constructing the application resources. Invalid configuration fails startup with a redacted message.

Exhaustion produces the existing unavailable responses; it does not create extra sessions. Liveness and the simple fixture endpoint do not use the pool. Spatial SQL failures roll back before reuse. Shutdown disposes the pool; a new lifespan creates new input/spatial resources. Workers/importers retain their existing connection behavior until the separate bounded Job implementation.

These are per-process limits. Serving still requires one Uvicorn process, the accepted Cloud Run revision/instance envelope and the global runtime SQL-role cap. A finite checkout wait is not an end-to-end request deadline or a demonstrated throughput guarantee.

## Local acceptance

Validation passed: **495 unit tests**, **160 integration tests**, Ruff lint/format, strict mypy over **57 source files**, and **565 relative documentation link targets**. The real Compose smoke also passed under `python -O`, including cold readiness, initialization, city/boundary/evidence, API recreation, checkpoint expiry, worker replay, database restart and optional Redis recovery. Its containers, network and recorded volume mounts were removed successfully.

`tests/integration/test_api_pool.py` creates a disposable database, migrates and imports through the real CLI roles, then serves through the restricted runtime login. It verifies:

- Holding both connections causes readiness, area, boundary and evidence requests, plus an uncached spatial query, to time out without extra sessions. All routes and the spatial query recover when slots are released.
- A real malformed-geometry SQL error rolls back; transaction status and local statement timeout reset before the same session is reused successfully.
- Terminating idle database sessions triggers successful replacement within the two-session bound.
- Shutdown leaves no tagged runtime sessions; another lifespan uses fresh resources and produces the same city result.

The existing real-entrypoint role test also covers a complete durable worker replay and matching read-only API snapshots. Reproduce against an isolated local PostGIS server with `uv run pytest -m integration -q tests/integration/test_api_pool.py tests/integration/test_demo_database.py`. No cloud credentials are required.

Managed Cloud Run saturation/overlap, service-identity authentication and bounded Job execution remain separate deployment checks. No cloud resources or SQL grants are changed by this implementation.

Deployment follow-up: [probe wiring and checkout tuning](../architecture/demo-cloud-resource-plan.md#probe-wiring-and-checkout-tuning) requires startup `/health/ready`, liveness `/health/live`, and managed concurrency-4 measurements before choosing the final checkout wait. The local pass does not establish a managed p95 or demonstrate that one second is sufficient there.

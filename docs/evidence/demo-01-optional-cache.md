# DEMO-01: Optional cache readiness

Date: 5 October 2026. Configuration and commands are in the [development guide](../development.md#run-the-fixture-demo-without-redis); progress belongs in the [delivery plan](../delivery-plan.md).

`CACHE_ENABLED` defaults to `true`. Enabled mode retains Redis readiness; disabled mode never constructs a Redis client and returns `redis: disabled`. Both modes require PostGIS. The Redis-free Compose overlay removes the startup dependency while retaining PostgreSQL and fixture initialization. This implements the cache-mode prerequisite in [ADR 0010](../adr/0010-hosted-fixture-demo.md), without adding caching, automatic fallback or cloud resources.

## Verification

- Ruff lint/format and mypy passed. The full local unit/API suite passed: **428 tests**, with 142 integration tests excluded from that command. Focused regressions cover flag defaults/validation, fail-fast API startup with sanitized errors, reuse of startup settings, disabled client construction, enabled ping failure, PostGIS failures and smoke cleanup.
- A real Uvicorn subprocess exits on invalid cache configuration before serving; its logs contain the configuration diagnostic without the invalid input value.
- `python -O scripts/compose_smoke.py` passed against real isolated PostGIS and Redis containers. It verified enabled-cache readiness, Redis outage returning 503 while city queries stay unchanged, then removed Redis and started the app with the no-cache overlay. No Redis container existed and readiness reported `disabled`; the integrated city result matched the enabled-mode result.
- With cache disabled, stopping PostgreSQL made readiness and city queries return 503 while liveness stayed available. Restarting PostgreSQL restored the same city result. Re-enabling cache recreated the API with Redis readiness and preserved city data.
- The same smoke retained its initializer, API recreation, proxy, durable checkpoint/expiry, replay and independent-worker database-restart checks. It removed its own stack/volume and retained local logs under `.local/compose-smoke/`.
- Resolved Compose configuration confirms default API dependencies are PostgreSQL, Redis and city-init; the no-cache app selects no Redis service and depends only on PostgreSQL and city-init. CI runs the same smoke plus the existing full checks.

Basic readiness still does not read or verify city imports. Hosted deployment must also check a real city response. The existing Starlette/httpx deprecation warning remains unrelated to this change; hosted IAP/Cloud SQL behavior is not established by these local checks.

# CITY-04 container and readiness follow-up

Date: 2026-10-05. Baseline: `e4c6ffd` (PR #8). Scope: local synthetic fixtures, real Docker Compose/PostGIS, database-owned import selection and dependency readiness.

## Reported baseline measurements

The maintainer reported these single local TestClient request durations while reviewing PR #8: city 0s approximately 0.11 s, 180s 0.33 s, 360s 0.59 s, and `/health/ready` 0.11 s. Their container finding came from Dockerfile/Compose inspection, not a built-image test.

## Follow-up measurements

A separate local TestClient process used the same city clocks and dependency readiness endpoint, making six sequential requests per endpoint. The first sample is shown separately; the median uses the next five. Images were building concurrently, so these are observations rather than a controlled before/after comparison.

| Request | First (s) | Median next five (s) |
| --- | --- | --- |
| City 0s | 0.1573 | 0.0421 |
| City 180s | 0.2628 | 0.1654 |
| City 360s | 0.3051 | 0.3145 |
| Readiness | 0.0577 | 0.0360 |

Reproduce after explicit migration/import with FastAPI TestClient: time `client.get` using `perf_counter`, assert 200, repeat six times, and report first and median of the remaining five. Test the three city URLs with `scenario=city&seconds=0`, `180`, `360`, then `/health/ready`. The spatial adapter's existing bounded geometry caches now survive between requests. Inputs remain read and integrity-checked per request; condition/receipt state remains request-local.

## Container verification

`python scripts/compose_smoke.py` built the API, initializer and UI images in a unique `urbanpulse-smoke-*` project. It verified:

- Healthy PostGIS/Redis allow `/health/ready` and the original `/api/v1/fixture` to respond before migrations/import; city remains 503.
- Full `--profile app up --wait` runs `city-init` first. The image contains migrations, and the completed import is selected in PostgreSQL.
- City, boundary and evidence endpoints respond; the web container proxies city API requests.
- Recreating the API without a shared initializer filesystem preserves exactly the same city result.
- Repeating initialization reuses/selects the complete import and preserves that result.

The script removes only its isolated containers/network/volume and retains logs under `.local/compose-smoke/`. It is also configured as a separate CI job. The normal development database and host servers are not used by that smoke stack.

## Automated checks

Ruff lint/format, mypy, web lint/format and the production build passed. All 340 unit/API tests, 40 real PostGIS integration tests and 32 Chromium Playwright tests passed. The isolated Compose smoke test also passed, including exact city-response equality through the UI proxy and after API recreation.

The review follow-up also passed the full Compose smoke under `python -O`: API and initializer share one project-scoped image, and the API healthcheck invokes its installed Python directly. Eight script regression cases verify malformed/mismatched responses, optimized-Python checks and cleanup failures. If cleanup also fails, the original failure remains primary with the cleanup error attached; a cleanup-only failure still fails the run.

## Remaining work

Input-history caching and incremental transition reconstruction, candidate-state copy cost for long planning history, and explicit versioned event-reference storage remain EVENT-01 acceptance work in the [delivery plan](../delivery-plan.md#event-01-follow-up-inputs-from-city-04-review). This change does not cache complete area snapshots or change domain/receipt semantics.

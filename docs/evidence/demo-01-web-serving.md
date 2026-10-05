# DEMO-01 compiled serving evidence

Date: 6 October 2026. Reproduce using the [serving runbook](../runbooks/web-serving.md).

The runtime packages compiled assets with a pinned Caddy image, proxies API/health paths on the same origin, and preserves fixture and failure semantics. Verification:

- Ruff lint/format, mypy, web ESLint/Prettier and **455 unit/API tests** passed; 142 database integration tests remain part of the separate CI integration job.
- **38 Playwright tests** passed against the Caddy image and real isolated PostGIS: all 32 existing city/weather/planning browser cases plus nested-path reload, compiled asset/cache behavior, missing/private paths, and proxied API/health/query/error semantics. Browser checks also reject inline scripts and cross-origin framing, verify origin-only Referer, and report no CSP violations while loading the three-domain map and reloading it.
- `python -O -m scripts.web_serving_smoke` passed using a non-default port and the default localhost upstream with a shared API/web network namespace. The runtime ran as non-root with a read-only root filesystem and capabilities dropped; Redis was absent.
- The documented Compose mode also passed on the default port with the `api:8000` DNS upstream, isolated data and cleanup.
- Security headers and absent `Server` were verified on HTML/assets, backend JSON success/errors, and missing-asset 404. Stopping the API produced 502 through ingress with the same security policy and no `Server`, while static HTML remained available. Stopping PostgreSQL produced readiness/city 503 with the same headers and API liveness 200. Both recovered to the same city response.
- `python -O scripts/web_build_smoke.py` passed actual/adversarial full-context inventories and the unchanged asset-export contract after adding the exact `Caddyfile` allowlist entry.
- Cleanup verified no project containers, networks, labelled volumes or recorded volume mounts remained, including Caddy's image-declared anonymous volumes. The successful rehearsal log is under `.local/web-serving-smoke/urbanpulse-smoke-266d5ee0dcf3/` in the verification checkout.

CI runs the serving browser and outage checks in its Compose job; no cloud credentials are needed.

The first rehearsal exposed a privileged-port file capability on the official Caddy binary that prevented execution with all capabilities dropped. The serving stage removes that capability before switching to a non-root user. Failed rehearsal resources were removed by the same project/mount-aware cleanup.

HSTS header emission was checked at the container boundary; browser enforcement through the TLS-terminating edge belongs to hosted acceptance. Hosted HTTPS/IAP, Cloud SQL and deployment identities require separate cloud acceptance; this evidence concerns the local container boundary.

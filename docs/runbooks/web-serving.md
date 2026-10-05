# Compiled web serving rehearsal

The `serving` target in `apps/web/Dockerfile` packages Caddy and compiled assets for the ingress boundary in [ADR 0010](../adr/0010-hosted-fixture-demo.md). Deployment progress is maintained in the [delivery plan](../delivery-plan.md). The default Docker target remains the local Vite development server; `assets` still exports files only.

## Runtime contract

| Setting or route | Behavior |
| --- | --- |
| `PORT` | HTTP listener on all interfaces; default `8080` |
| `API_UPSTREAM` | Backend address; default `127.0.0.1:8000` for an API sidecar, `api:8000` in the local serving override |
| `/api`, `/api/*`, `/health`, `/health/*` | Preserve backend path/query, JSON and status; responses are not cached |
| `/health/live` | API process liveness; a stopped API produces a proxy error |
| `/health/ready` | API dependency readiness; unavailable PostGIS returns 503, disconnected API returns 502 |
| `/assets/*` | Serve compiled assets; existing assets are immutable-cacheable, missing assets return 404 |
| Other UI paths | Serve the SPA fallback, including nested-path reloads; HTML revalidates |

The image runs as UID/GID `10001:10001`, with no Node runtime, source tree or package dependencies copied into the serving stage. Caddy's admin endpoint, automatic HTTPS and config persistence are disabled. Its image is pinned by manifest digest and its unnecessary privileged-port capability is removed. The local rehearsal drops capabilities and uses a read-only root filesystem. The exact-file build-context allowlist includes only the new `Caddyfile` alongside existing build inputs.

### Response security

The ingress applies one deferred header policy to HTML, assets, backend responses and Caddy-generated errors:

- CSP limits scripts, workers, connections and stylesheets to the same origin; disables objects, base overrides and all framing; and allows images from local, `data:` and `blob:` sources. MapLibre's emitted worker uses a same-origin URL. Only style **attributes** allow inline values for React/MapLibre marker positioning; inline scripts, inline stylesheets and script evaluation remain blocked.
- `frame-ancestors 'none'` and `X-Frame-Options: DENY` prevent embedding, including for authenticated users.
- `Referrer-Policy: strict-origin-when-cross-origin` sends only the origin on cross-origin navigation, excluding the scenario query.
- `Strict-Transport-Security: max-age=31536000` applies to the hosted HTTPS domain, without subdomain or preload opt-in. Caddy sends it for the TLS-terminating edge; browsers ignore it on local HTTP.
- `X-Content-Type-Options: nosniff` remains enabled. `Server` is removed at response write time, including 404/502 error routes.

Caddy-generated errors retain their status and return only the status code/text with `Cache-Control: no-store`. Backend JSON errors pass through with their original body/status and the same security headers.

Cloud Run will terminate HTTPS and enforce IAP. This local container provides HTTP only and performs no user authentication; bind the rehearsal to loopback. Service configuration, IAP, Cloud SQL, identities, migration Jobs, image publishing and revision promotion belong to subsequent deployment work. No cloud compatibility or access-control acceptance is established by local tests.

## Run locally

Use an isolated project so the fixture import cannot target the usual development database:

```powershell
docker compose --project-name urbanpulse-serving -f compose.yaml -f compose.no-cache.yaml -f compose.serving.yaml --profile app up --build -d --wait
```

Open `http://127.0.0.1:8080/?scenario=city`. The initializer imports synthetic fixtures. Only the web port is published; PostgreSQL and API ports remain internal, and Redis is absent. The ordinary development command and its hot reload remain available separately.

Remove only this rehearsal's containers and data when finished:

```powershell
docker compose --project-name urbanpulse-serving -f compose.yaml -f compose.no-cache.yaml -f compose.serving.yaml --profile "*" down --volumes --remove-orphans
```

## Reproduce acceptance

Install the locked frontend dependencies and Playwright Chromium once, then run from the repository root:

```powershell
Push-Location apps/web
npm.cmd ci
npx.cmd playwright install chromium
Pop-Location
python -O -m scripts.web_serving_smoke
```

The smoke owns a unique project and random loopback port. It runs the existing city/weather/planning browser suite plus serving-specific checks against the compiled image. Its API shares the web container's network namespace, exercising the default localhost upstream and a non-default `PORT`. It checks CSP compatibility, rejected inline scripts and cross-origin framing, origin-only Referer, and security headers on successful/error responses. It tests API and database outage/recovery through the ingress, verifies non-root execution and no Redis, and tears down all profiles with recorded anonymous-volume checks. Images and build caches remain available for reuse. Docker logs remain under `.local/web-serving-smoke/`; browser failure traces remain in `apps/web/test-results/serving/`.

The separate `python -O scripts/web_build_smoke.py` checks both actual and adversarial build contexts and the static export. [Serving evidence](../evidence/demo-01-web-serving.md) records measured results.

References: [Caddy response headers](https://caddyserver.com/docs/caddyfile/directives/header), [Caddy error routes](https://caddyserver.com/docs/caddyfile/directives/handle_errors), [MapLibre CSP requirements](https://maplibre.org/maplibre-gl-js/docs/), [HSTS browser behavior](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Strict-Transport-Security), [Caddy SPA/proxy patterns](https://caddyserver.com/docs/caddyfile/patterns), [Caddy global options](https://caddyserver.com/docs/caddyfile/options), [Cloud Run container contract](https://docs.cloud.google.com/run/docs/container-contract).

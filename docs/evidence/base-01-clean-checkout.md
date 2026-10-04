# BASE-01: Independent clean-checkout verification

Recorded: 4 October 2026 (Australia/Sydney).

Verified revision: [b2a390b](https://github.com/maxtsec/urban-pulse-au/commit/b2a390bface82a418094d8fcf7843f8bd42796a9). The rehearsal cloned GitHub main into a new directory and verified that revision before setup. No application code changed during the rehearsal.

## Conditions

- Windows x64; Python 3.12.15, uv 0.12.23, Node.js 24.19.0 and npm 11.17.0.
- Docker Engine 29.8.1 and Compose 5.5.1; PostGIS 3.5 and the configured Redis 7.4 image.
- No pre-existing virtual environment, node_modules, .env or generated data in the clone.
- Existing package caches, Python installation and Docker images were available. This is a fresh checkout and database rehearsal, not a fresh-machine or cold-cache benchmark.
- Docker Desktop was initially stopped and was started before service checks. Its startup time is excluded from the service timing.
- Dedicated Compose project `urbanpulse-base01-b2a390b` with a new database volume, PostgreSQL port 15432 and Redis port 16379. HTTP smoke used free ports 8000 and 5173.
- Three synthetic observations, preserving delays of 120, null and -30 seconds.

## Results

Timings are one observed run, measured around each command with a stopwatch.

| Step         | Command or check                                                     | Result                                                                         | Elapsed   |
| ------------ | -------------------------------------------------------------------- | ------------------------------------------------------------------------------ | --------- |
| Clone        | `git clone --single-branch --branch main` from the public repository | Correct revision; empty dependency/generated directories                       | 1.27 s    |
| Restore      | `scripts/setup.ps1`                                                  | Locked Python/frontend dependencies restored; sample .env created              | 23.95 s   |
| Code checks  | `scripts/check.ps1`                                                  | Ruff, mypy, 2 pytest tests, ESLint, Prettier, TypeScript and Vite build passed | 57.60 s   |
| Services     | `scripts/services-smoke.ps1` with isolated Compose configuration     | Healthy containers, PostGIS version query and Redis PONG                       | 7.97 s    |
| Readiness    | FastAPI TestClient request to `/health/ready`                        | HTTP 200 with real isolated PostGIS and Redis                                  | Not timed |
| HTTP smoke   | `uv run --locked python scripts/smoke.py`                            | Liveness, Vite HTML and labelled fixture through the proxy                     | 2.36 s    |
| Cleanup      | `docker compose down --volumes` for the rehearsal project only       | Test containers, network and volumes removed                                   | Not timed |
| Working tree | `git status --porcelain`                                             | Empty after setup and checks                                                   | Not timed |

Pytest and TestClient emitted the existing Starlette/HTTPX deprecation warning. Both tests and the readiness check passed. No dependency change was needed.

The readiness assertion exercised the ASGI route with real database/cache connections. The separate HTTP smoke checked actual API/Vite processes; it did not run a browser.

## Reproduction and evidence

Follow the [clean-checkout walkthrough](../demos/clean-checkout.md), pinned to the revision above. The [baseline CI run](https://github.com/maxtsec/urban-pulse-au/actions/runs/37195800723) also passed on that revision; its Linux checks do not include the Windows service/HTTP rehearsal.

Local command logs and measurements were retained under ignored `.local/base01/`: `setup.log`, `checks.log`, `services.log`, `http.log`, `cleanup.log` and `measurements.json`. These are local working evidence, not public CI artifacts. The clone's tracked files and lockfiles remained unchanged.

Before and after the isolated service run, the original development containers retained their IDs, status and start times, and the original named-volume list was unchanged. Docker Desktop remains running; the original development containers remained stopped.

## Scope

This verifies BASE-01's clean-checkout restore, local checks and service/HTTP acceptance. Browser interaction, application container images, cloud/provider access, warehouse execution and failure recovery remain separate acceptance cases in the [testing strategy](../testing-strategy.md). Phase completion and release/tag status are tracked in the [delivery plan](../delivery-plan.md#milestones-and-exit-evidence).

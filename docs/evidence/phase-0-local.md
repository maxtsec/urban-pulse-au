# Phase 0 local evidence

Recorded: 4 October 2026 (Australia/Sydney), for the city intelligence initial baseline containing this record. Checks ran against the final application code before its initial commit; documentation and evidence were finalised afterwards. This is a local development checkpoint, not a tagged release.

## Conditions

- Windows development machine with existing dependencies, caches and database containers; not an independent clean-checkout rehearsal.
- Python 3.12.15, uv 0.12.23, Node.js 24.19.0 and npm 11.17.0 from the installed development environment.
- Docker CLI 29.8.1; PostGIS 3.5 and Redis respond through local Compose services.
- Three synthetic observations, with delay values 120, null and -30 seconds.

## Observed checks

| Check                                                                                    | Result | Evidence scope                                                                                           |
| ---------------------------------------------------------------------------------------- | ------ | -------------------------------------------------------------------------------------------------------- |
| `scripts/check.ps1`                                                                      | Passed | Ruff lint/format, mypy, 2 pytest tests, ESLint, Prettier, TypeScript and Vite build                      |
| `scripts/services-smoke.ps1`                                                             | Passed | Healthy PostGIS/Redis containers, PostGIS version query and Redis PONG                                   |
| `scripts/smoke.py`                                                                       | Passed | API liveness, Vite HTML and synthetic response through the Vite proxy                                    |
| `uv run --locked python -m workers.ingestion.main --once`                                | Passed | Content-addressed local synthetic capture; repeat identity also covered by unit test                     |
| Dagster command from [demo](../demos/phase-0.md#independent-data-tool-smoke)             | Passed | Executed documented block; successful materialization, 3 Parquet rows and 1 null                         |
| Offline dbt parse from [development guide](../development.md#checks-and-analytics-smoke) | Passed | dbt 1.12.5 with BigQuery adapter 1.12.1; no cloud query                                                  |
| Markdown validation                                                                      | Passed | Baseline snapshot: 12 documents and 62 relative links/anchors; balanced fences and no control characters |
| PowerShell example syntax                                                                | Passed | 15 fenced example blocks parsed with the full PowerShell parser                                          |
| Markdown formatting                                                                      | Passed | Repository-local Prettier used for README, brief and documentation                                       |

Pytest reports one upstream FastAPI/Starlette test-client deprecation warning about HTTPX; both tests pass. The initial sandboxed PowerShell parser attempt was blocked by restricted language mode; rerunning with full PowerShell succeeded. This does not imply every documented cloud command was executed.

HTTP smoke terminates its temporary servers. Service smoke leaves PostGIS and Redis running on loopback. Worker/Parquet outputs and dbt parse artifacts stay in ignored local/generated paths; existing database volumes are preserved.

## Validation scope

These results cover local fixture/tooling paths on the installed development machine. Clean-checkout setup, browser interaction, application containers, provider/cloud integration and performance were outside this run. The two unit tests cover fixture labeling, unknown/negative delay preservation and repeated file identity. Product progress is maintained in the [delivery plan](../delivery-plan.md#implementation-baseline).

## Documentation review

The v1 documentation check passed on 4 October 2026: 12 Markdown files, 73 relative links/anchors, v1 references, balanced fences, text encoding, Prettier formatting and 15 PowerShell examples. Executable code and dependency locks are unchanged. Before publication, scripts/check.ps1 was rerun successfully: Ruff, mypy, 2 pytest tests, frontend lint/format and TypeScript/Vite build. Service, HTTP, Dagster and dbt results above remain from the earlier baseline run.

## Next evidence record

Record the work item, acceptance case, source commit/release and working-tree state, date/timezone, environment, input identities, exact commands and results, limitations, relevant logs/CI/recording and cleanup. Preserve failed/skipped checks.

For city demonstrations, add the selected area/boundary version, per-domain coverage and source timestamps, status-rule version and fixture/live label. For performance, state workload, cache conditions and actual measured duration; an offline parse or dry-run estimate is not an execution benchmark.

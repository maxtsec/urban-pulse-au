# EVENT-01 city checkpoint evidence

Date: 2026-10-05. Baseline: `b4e50a0` (PR #12). Scope: accepted ADR 0009 fixture runs and Location Intelligence. [Reproduction and interpretation](../runbooks/city-checkpoints.md); progress stays in the [delivery plan](../delivery-plan.md).

## Verified behavior

Real PostgreSQL/PostGIS tests compare every completed checkpoint of all seven scenarios with synchronous city replay. Comparisons include the full snapshot, reasons, coverage, planning profile, map observations, diagnostics and exact area-event identities, excluding only the delivery/recovery mechanism labels. Two concurrent workers complete one retained result per checkpoint.

A dead-lettered input blocks its own ordered run while another run completes. Operator replay releases that barrier. Per-consumer dependencies preserve independent progress and do not charge attempts while blocked. Tests reject cross-context or missing-consumer dependencies, preserve pending unordered deliveries across migration 0007 and refuse downgrade that would erase dependency history. Missing received inputs and incompatible run versions cannot produce a completed checkpoint.

Separate Python processes are terminated inside producer staging, after writing a checkpoint but before commit, and after checkpoint commit. Fresh worker processes resume from database state. Uncommitted publication/cursor/result writes disappear together; committed results and derived events appear once. Failure after staging the next checkpoint also rolls back the completed checkpoint and derived publication.

The weather-outage run changes from Degraded at 239 to Unknown at 240 without adding a weather-source publication. Timer targets use the shared position freshness policy and received warning validity boundaries. Independent synchronous reads at 0 and 360, plus durable-run inspection, change neither queue contents nor run clocks.

Review regressions exercise result-publication conflicts, invalid area events, missing delivery references and failure during next-checkpoint activation. Each affected transaction rolls back and records a checkpoint error while another run completes. Database failures still propagate to polling backoff without marking the checkpoint invalid. Separate database connections acquire both advisory and row locks during input loading and spatial evaluation, proving that preparation holds neither. Paused preparations resume after another worker completes or a producer advances; neither a stale result nor a late error can overwrite the newer run state.

Advancement tests complete clock 300, then verify that only missing clocks after 300 are prepared for target 330. Repeating target 330 reuses its pending manifests. Interleaved old/new envelopes retain one ordered delivery chain without a run-wide publication list. A fresh migration is checked to omit that unused column. The required per-checkpoint references and bounded projection reconstruction remain.

## Local check results

- Ruff lint/format and mypy passed.
- Unit/API suite: 387 passed, including seven clock-boundary cases.
- Real PostgreSQL/PostGIS integration suite: 134 passed, including 19 city-run, five ordered-delivery and 12 checkpoint review regressions.
- Frontend lint/format and production build passed; 32 Playwright browser tests passed.
- The isolated Compose smoke passed under `python -O`: it compares the three-domain durable run with HTTP results, stops its worker, stages warning expiry and recreates the worker to complete it. It also retains the previous cold-readiness, initializer, proxy, API recreation, replay and database-restart checks. Run with `python -O scripts/compose_smoke.py` or use the PR's Compose CI job. The full container check passed and its generated stack/volume were removed.

Existing non-failing warnings concern the TestClient dependency transition and the frontend bundle size. Fixture checks use no provider keys or cloud resources.

## Bounded timing and retained run

Before these review fixes, on the local Windows/Docker PostGIS development setup, a fresh `city` run from 0 to 360 took **1.058 seconds to stage** and **4.993 seconds to drain**, including 49 non-idle worker steps, 17 checkpoints and nine area transitions. It finished with Unknown current conditions, matching the fixture's incomplete current coverage. These are single-run wall-clock measurements, not latency targets or load-test results.

The completed run `event01-city-checkpoints-01` remains in the local development database for `workers.city.main inspect`; no API import pointer was changed by its creation/advancement. Test runs use separate generated database schemas, and the Compose smoke owns its own generated stack and volume.

Reconstruction still reloads and validates the bounded input export and deep-copies candidate projections. Growing planning-history measurements, cache invalidation/failure tests and any optimization are separate follow-up work. This evidence establishes a synthetic durable recovery path; browser replay remains request-local and live-source enablement remains separately gated.

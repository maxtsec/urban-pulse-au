# Delivery plan

Aligned with brief v1. Progress is maintained here and in the [README progress table](../README.md#progress). Work IDs are planning references, not GitHub issue numbers.

## Milestones and exit evidence

| Phase | Deliverable                                       | Status and exit evidence                                                                                                            |
| ----- | ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| 0     | Reproducible local foundation                     | Local scaffold verified; independent clean-checkout restore and recorded timing remain                                              |
| 1     | Area/map foundation and transport fixture slice   | Planned: fixture-to-area UI path with provenance, freshness and replay tests                                                        |
| 2     | Integrated city MVP with shared in-process events | Planned: weather and planning in the same area view; event contract tests, status reasons, expiry and coverage                      |
| 3     | Durable event reliability                         | Planned: reviewed delivery adapter, idempotent consumers, duplicate/out-of-order/retry/dead-letter/crash/replay evidence            |
| 4     | Full application cloud delivery                   | Planned: repeatable API/UI/worker/pipeline deployment, scoped identities, migrations, telemetry, rollback and operating budget      |
| 5     | Historical city intelligence                      | Planned: real BigQuery/dbt work over retained history, bounded backfill, metric lineage, publication gating and governance evidence |
| 6     | Evaluated enhancements                            | Later: separately approved scores, AI tools or subscriptions with measured acceptance results                                       |

Phases 1-2 form the city MVP; phases 3-5 complete the first city release. Security, source permissions, tests and baseline telemetry apply from the first feature. Each completed phase receives a Git tag, release notes, a reproducible demo and an evidence record tied to that tag.

## Early capture track

This parallel track targets phases 1-2 and has its own acceptance criteria. Aim to resolve A-06 at the start of phase 1, alongside source feasibility. CLOUD-01 provisions one GCS bucket and one small continuously running capture worker with scoped identity, secret access, lifecycle/retention policy, provider request budgets and basic failure alerts. The host, region and budget are chosen before provisioning.

Target phase 1 for transport capture and phase 2 for weather/planning, enabling each source after its access decision and cloud readiness. Record capture manifests, source/capture timestamps, checksums, earliest retained date and gaps. Verify restart/retry and retrieval of stored bytes. Use idempotent object writes and a durable capture ledger/manifest scheme reviewed with A-03; the early collector does not depend on a hosted API, event broker or warehouse.

Capture infrastructure is managed in code and adopted by phase 4 deployment rather than replaced. Do not wait for full application hosting to accumulate history. If access or hosting blocks collection, keep the track open and record the gap and its phase 5 impact. Phase 1 can close when its fixture-to-area UI acceptance passes; live source permission, CLOUD-01 and its cloud decisions do not gate that exit. Demonstrating a live city MVP still requires verified access and coverage for the selected sources.

## Immediate work queue

| ID          | Phase                | Scope                                              | Depends on                                                          | Acceptance                                                                                                                          |
| ----------- | -------------------- | -------------------------------------------------- | ------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| BASE-01     | 0                    | Rehearse baseline in an independent clean checkout | Local scaffold                                                      | Restore locks; checks/service/HTTP pass; record environment and duration                                                            |
| SRC-01      | 1                    | Verify three source domains and common geography   | Source register                                                     | Terms/cadence/coverage evidence; compare CBD, Southbank and Carlton; evaluate vehicle positions                                     |
| CLOUD-01    | Parallel; target 1-2 | Minimal continuous cloud capture                   | Accepted source/retention policy; A-03 capture contract; early A-06 | Bucket + small worker run within budget; stored payload/manifest retrieved; restart, gaps and retention verified                    |
| AREA-01     | 1                    | Agree area identity and map experience             | SRC-01; A-01/A-02                                                   | Boundary version, spatial rules, accessible map/panel and position freshness examples                                               |
| CONTRACT-01 | 1                    | Define domain, area and event contracts            | SRC-01; A-03/A-04                                                   | Shared event envelope/payload versions, identity, time/expiry, deduplication and handler outcomes specified; transport port defined |
| CITY-01     | 1                    | Area foundation and transport slice                | AREA-01; transport contract                                         | Capture -> projection -> area map; replay/freshness tested; vehicle-position option recorded                                        |
| CITY-02     | 2                    | Weather warning slice                              | Warning contract; CITY-01                                           | Spatial match, warning update/cancellation/expiry and stale-source behavior                                                         |
| CITY-03     | 2                    | Planning/infrastructure slice                      | Planning contract; CITY-01                                          | Status and as-of dates preserved; supported geography visible                                                                       |
| CITY-04     | 2                    | Area composition through in-process events         | CITY-02/03; CONTRACT-01; A-04                                       | Same envelope through publisher/handler ports; duplicate/older-event tests; time-driven refresh; full recomputation after restart   |
| EVENT-01    | 3                    | Durable event delivery adapter and recovery        | A-05; CONTRACT-01; CITY-04                                          | Existing domain contracts unchanged; publication intent, consumer ledger, DLQ, crash recovery and controlled replay verified        |
| CLOUD-02    | 4                    | Full application deployment                        | CLOUD-01; EVENT-01; approved deployment design                      | Adopt capture resources; scoped API/UI/runtime delivery, migrations, telemetry, recovery and cost evidence                          |
| HIST-01     | 5                    | Historical models and publication                  | Retained CLOUD-01 history; warehouse access; A-07                   | Coverage/gaps stated; BigQuery/dbt integration, bounded backfill and failed-publication protection                                  |

The in-process adapter does not promise durable delivery. Phase 2 must reconcile area projections from persisted domain state after a restart or handler failure. Phase 3 adds durable publication/acknowledgement and consumer state through adapters and application wiring, without coupling domain rules to a broker.

## Decisions needed before dependent work

| ID   | Decision and timing                                                         | Options and recommendation                                                                                                                                                                                                                                             | Blocks                                        |
| ---- | --------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------- |
| A-01 | Pilot boundary, phase 1                                                     | Compare published CBD, Southbank and Carlton boundaries within City of Melbourne. Use Southbank as the demo example; choose actual scope after three-domain overlap checks.                                                                                            | Area IDs, joins and schemas                   |
| A-02 | Transport feed and map tiles, phase 1                                       | Compare a vehicle-position-capable feed plus compatible status data against status-only coverage. Prefer positions for a visibly active map when access, identifiers, cadence and rate budget support it. Compare hosted/self-hosted tiles separately.                 | Feed adapter and public map                   |
| A-03 | Record identity, capture manifest, API and event envelope, phase 1          | Preserve provider semantics; agree required envelope fields and payload versions in CONTRACT-01. Define the capture-only contract early so collection need not wait for the full area API.                                                                             | Capture metadata, schemas and event consumers |
| A-04 | Area status and timing targets, phases 1-2                                  | Prefer explained categorical status over a numerical score; agree rules and the proposed area/expiry lag targets before acceptance tests.                                                                                                                              | Derived status and measured acceptance        |
| A-05 | Durable delivery, before phase 3                                            | Compare database outbox/consumer ledger with managed broker-backed delivery. Keep the shared envelope and publisher/handler ports; choose by replay, isolation and operational needs.                                                                                  | Cross-process delivery and recovery           |
| A-06 | Minimal capture cloud region, identities, budget and host, start of phase 1 | Compare a small persistent VM/container host with a managed always-running worker. Prefer the smallest suitable continuous runtime; select service/region/cost values after comparison. Finite scheduled jobs are a fallback requiring an explicit freshness decision. | CLOUD-01 and history accumulation             |
| A-07 | Historical grain, sampling and area aggregation, before phase 5             | Begin with a defined transport history metric plus coverage; area metrics require separate definitions.                                                                                                                                                                | dbt facts/marts and comparisons               |

Full deployment revisits topology in CLOUD-02 while preserving the early capture decisions where suitable. Source licensing and retention require acceptance before live collection. SSE is the proposed one-way UI transport when polling becomes insufficient; WebSockets, a gateway and additional CQRS infrastructure need concrete requirements.

## Implementation baseline

The current executable baseline serves a synthetic transport fixture. City map/layers, area status, live adapters, event delivery, migrations and cloud provisioning are upcoming work. There is no hosted demonstration or recording.

The fixture API reads JSON directly through the Vite proxy into a React table. The worker independently copies that JSON into content-addressed local storage; Dagster independently writes Parquet. These are separate smoke paths. Readiness currently requires both PostGIS and Redis. MapLibre/ECharts and telemetry libraries are installed; views and instrumentation follow their feature work. Shared ROOT configuration still comes from the API entry point and should move to a neutral module during the first related structural change.

See the [local evidence](evidence/phase-0-local.md) for the dated check results and scope.

## Feature specification and completion

Every scheduled feature states the user outcome, scope, Given/When/Then cases, affected contracts, pending decisions, tests and demonstration steps. Include missing/stale and relevant failure cases.

Ready for review means relevant checks pass, affected documents are updated and migration/recovery risks are recorded. Update progress in this document and README; other documents link here. On phase completion, create its Git tag and attach release notes, demo/evidence and the actual CI run to that revision. Document version v1 is independent of software release tags.

A replay example: process the same warning twice, then an older revision. There must be one current effect, the newer warning remains authoritative, and every attempt is traceable. A file-hash test alone does not satisfy that acceptance case.

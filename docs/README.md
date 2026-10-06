# Documentation

UrbanPulse is a Melbourne city intelligence project integrating transport, weather/hazards and planning/infrastructure. Maintain progress only in the [README progress table](../README.md#progress) and [delivery plan](delivery-plan.md).

## Reading paths

For product review: [project brief](../project_brief.md) → [city MVP scenario](demos/city-mvp.md) → [delivery plan](delivery-plan.md).

For development: [development guide](development.md) → [architecture](architecture/overview.md) → [testing strategy](testing-strategy.md) → the relevant decision/source record.

For local setup demonstration: [Phase 0 walkthrough](demos/phase-0.md) and [local evidence](evidence/phase-0-local.md).

For reproducibility: [clean-checkout walkthrough](demos/clean-checkout.md) and [BASE-01 evidence](evidence/base-01-clean-checkout.md).

For pilot/source review: [SRC-01 comparison](evidence/src-01-source-feasibility.md), [accepted Southbank/Tram decision](adr/0002-southbank-tram-pilot.md) and [source enablement gates](source-register.md).

For contract review: [ADR 0003](adr/0003-cloudevents-and-area-conditions.md), [area/map contract](architecture/area-contract.md), [capture/event contract](architecture/capture-event-contract.md) and [early capture hosting comparison](architecture/early-capture-options.md).

For the runnable city view: [CITY-01 walkthrough](demos/city-01.md), [fixture map decision](adr/0004-southbank-fixture-map.md) and [test evidence](evidence/city-01-fixture-map.md).

For weather-source evolution: [ADR 0005](adr/0005-weather-source-policy.md) → [source enablement gates](source-register.md#weather-enablement-evidence) → [area weather policy](architecture/area-contract.md#weather-source-policy).

For the integrated weather replay: [CITY-02 walkthrough](demos/city-02.md), [fixture contract](architecture/weather-fixture-contract.md), [ADR 0006](adr/0006-weather-fixture-spatial-and-freshness.md) and [evidence](evidence/city-02-weather.md).

For the planning slice: [ADR 0007](adr/0007-planning-fixture-profile.md), [planning contract](architecture/planning-fixture-contract.md) and [CITY-03 walkthrough](demos/city-03.md).

For event composition: [ADR 0008](adr/0008-in-process-city-composition.md), [CITY-04 acceptance specification](architecture/city-04-composition.md), [recovery demo](demos/city-04.md) and [verification evidence](evidence/city-04-composition.md).

For durable delivery design: [ADR 0009 options](adr/0009-durable-event-delivery.md) and [EVENT-01 acceptance cases](architecture/event-01-durable-delivery.md).

For worker operations: [recovery runbook](runbooks/event-recovery.md) and [process/database evidence](evidence/event-01-worker-recovery.md). For the integrated city worker, use the [checkpoint walkthrough](runbooks/city-checkpoints.md).

For replay performance: [bounded history measurements and reproduction](evidence/event-01-performance.md) and [planning copy comparison](evidence/event-01-planning-copy-cost.md).

For Phase 3 verification: [acceptance map](evidence/phase-3-acceptance.md). For production V1: [release policy](delivery-plan.md#release-policy).

For the hosted fixture demo: [DEMO-01 accepted hosting and deployment design](adr/0010-hosted-fixture-demo.md), [image publishing operations](runbooks/image-publishing.md) and [publication evidence](evidence/demo-01-image-publishing.md) and [accepted resource choices](adr/0012-managed-demo-resource-profile.md), the [resource plan](architecture/demo-cloud-resource-plan.md) and [foundation operations](runbooks/demo-foundation.md), followed by [private database initialization](runbooks/demo-database.md).

For the animated 3D map: [ADR 0011](adr/0011-southbank-building-massing.md) → [MAP-02 input contract proposal](architecture/tram-animation-input-contract.md) → [map context sources](source-register.md#map-context-sources).

## Document responsibilities

| Document                                                 | Owns                                                               | Update when                                             |
| -------------------------------------------------------- | ------------------------------------------------------------------ | ------------------------------------------------------- |
| [Project brief](../project_brief.md)                     | Product scope, selected technology and release requirements        | Product direction or a major constraint changes         |
| [Delivery plan](delivery-plan.md)                        | Milestones, dependencies and unresolved decisions                  | Scope, priority or completion evidence changes          |
| [Architecture](architecture/overview.md)                 | Domain ownership, contracts and data flow                          | A boundary, runtime or data path changes                |
| [ADR 0001](adr/0001-city-intelligence-scope.md)          | Accepted integrated product scope and consequences                 | A later decision supersedes it                          |
| [ADR 0002](adr/0002-southbank-tram-pilot.md)             | Accepted Southbank CLUE pilot and initial tram scope               | The architect changes the pilot or transport scope      |
| [ADR 0003](adr/0003-cloudevents-and-area-conditions.md) | Accepted CloudEvents format and separate condition/coverage principle | A later decision supersedes either principle |
| [ADR 0004](adr/0004-southbank-fixture-map.md) | Accepted fixture identity, point membership, local map and age policy | Fixture rules change through architect review |
| [CITY-01 walkthrough](demos/city-01.md) | Feature scope, acceptance cases, local replay and query details | Fixture behavior or reproduction steps change |
| [CITY-01 evidence](evidence/city-01-fixture-map.md) | Dated spatial/browser results and verification limits | A new checkpoint is verified |
| [ADR 0005](adr/0005-weather-source-policy.md) | Accepted weather-source roles, warning severity/coverage and provider evolution | Source scope or assessment policy changes |
| [ADR 0006](adr/0006-weather-fixture-spatial-and-freshness.md) | Accepted positive-area warning overlap and authored fixture freshness | Spatial or freshness policy changes |
| [Weather fixture contract](architecture/weather-fixture-contract.md) | Weather payloads, replay, receipt semantics and API additions | Weather contracts or projection behavior changes |
| [CITY-02 walkthrough](demos/city-02.md) | Integrated weather demo and acceptance cases | Fixture behavior or reproduction steps change |
| [CITY-02 evidence](evidence/city-02-weather.md) | Dated weather, spatial and browser verification | A new checkpoint is verified |
| [ADR 0007](adr/0007-planning-fixture-profile.md) | Accepted planning fixture scope, point membership and snapshot absence | Planning policy changes |
| [Planning fixture contract](architecture/planning-fixture-contract.md) | Snapshot publication, atomic capture/profile semantics and API additions | Planning contracts or projection behavior changes |
| [CITY-03 walkthrough](demos/city-03.md) | Three-domain fixture demo and planning acceptance cases | Fixture behavior or reproduction steps change |
| [CITY-03 evidence](evidence/city-03-planning.md) | Dated planning, spatial and browser verification | A new checkpoint is verified |
| [ADR 0008](adr/0008-in-process-city-composition.md) | Accepted persisted inputs, in-process handlers and reconstruction scope | The architect selects or revises the recovery design |
| [CITY-04 specification](architecture/city-04-composition.md) | Implementation sequence, failure/restart acceptance and demo plan | Composition scope or acceptance cases change |
| [CITY-04 demo](demos/city-04.md) | Reproducible event/expiry/restart walkthrough | Recovery commands or observable behavior change |
| [CITY-04 evidence](evidence/city-04-composition.md) | Dated delivery/persistence/browser results and limits | A new checkpoint is verified |
| [CITY-04 Compose evidence](evidence/city-04-compose.md) | Container startup/recreation checks, readiness boundary and request timings | Container behavior or verified measurements change |
| [Area contract](architecture/area-contract.md) | Area identity, spatial rules, map/panel behavior and condition examples | Pilot semantics or API proposal changes |
| [Capture/event contract](architecture/capture-event-contract.md) | Capture identities/recovery proposal and integration wire profile | Contract, compatibility or recovery design changes |
| [Early capture options](architecture/early-capture-options.md) | Hosting trade-offs, workload assumptions and A-06 proposal | Host decision or measured resource requirements change |
| [Source register](source-register.md)                    | Provider evidence, coverage, access and open questions             | A source is evaluated, enabled or changes terms         |
| [Development guide](development.md)                      | Runnable setup, configuration and troubleshooting                  | Tooling or commands change                              |
| [Testing strategy](testing-strategy.md)                  | Existing checks and required feature coverage                      | Behavior or a service boundary changes                  |
| [Phase 0 demo](demos/phase-0.md)                         | Tagged phase-0 baseline walkthrough                                    | The current baseline changes                            |
| [Clean-checkout walkthrough](demos/clean-checkout.md)    | Isolated baseline reproduction and cleanup procedure               | Reproduction steps or the referenced checkpoint change  |
| [City MVP demo](demos/city-mvp.md)                       | Cross-domain acceptance scenario and evidence                      | Product acceptance rules are agreed or implemented      |
| [Local evidence](evidence/phase-0-local.md)              | Actual checks and their limits                                     | A new verification checkpoint is recorded               |
| [BASE-01 evidence](evidence/base-01-clean-checkout.md)   | Dated clean-checkout results, measurements and verification scope  | A new clean-checkout checkpoint is recorded             |
| [SRC-01 evidence](evidence/src-01-source-feasibility.md) | Official source findings, pilot comparison and reproduction method | Source evidence changes or a new comparison is measured |
| [ADR 0009](adr/0009-durable-event-delivery.md) | Durable transport decision and transaction/recovery model | Architect reviews durable delivery scope |
| [EVENT-01 specification](architecture/event-01-durable-delivery.md) | Implementation sequence and crash/concurrency/replay acceptance cases | Durable recovery behavior or test scope changes |
| [Observation storage](architecture/observation-storage.md) | Versioned event slots, migration compatibility and rollback rules | Stored observation format changes |
| [Observation storage evidence](evidence/event-01-observation-storage.md) | Migration, integrity and city compatibility results | Storage verification changes |
| [Outbox and ledger](architecture/outbox-ledger.md) | Publication/receipt transaction boundaries, claim lifecycle and upgrade behavior | Durable persistence semantics change |
| [Outbox/ledger evidence](evidence/event-01-outbox-ledger.md) | Real database concurrency, rollback and lease checks | Delivery repository verification changes |
| [Worker recovery runbook](runbooks/event-recovery.md) | Worker commands, retry/replay semantics and migration operations | Recovery operations change |
| [Worker recovery evidence](evidence/event-01-worker-recovery.md) | Process-kill, scheduling and operator verification | A recovery checkpoint is verified |
| [City checkpoint runbook](runbooks/city-checkpoints.md) | Durable run commands, clock/result semantics, migration and recovery | City worker operations change |
| [City checkpoint evidence](evidence/event-01-city-checkpoints.md) | City equivalence, ordered barriers, process crashes and Compose expiry | A city recovery checkpoint is verified |
| [EVENT-01 performance evidence](evidence/event-01-performance.md) | Reproducible history workloads, timing samples, copy profiling and optimization priorities | Replay implementation or verified measurements change |
| [Planning copy evidence](evidence/event-01-planning-copy-cost.md) | Immutable retained history, rollback guarantees and before/after measurements | Planning representation or verified performance changes |
| [ADR 0010: hosted fixture demo](adr/0010-hosted-fixture-demo.md) | Accepted managed hosting/IAP, image identity, deployment and rollback acceptance | Accepted topology or deployment requirements change |
| [DEMO-01 web packaging evidence](evidence/demo-01-web-build.md) | Static asset target, build-context exclusions and container verification | Web packaging or its verified checks change |
| [Compiled web serving](runbooks/web-serving.md) | Runtime settings, local rehearsal, route/cache behavior and failure checks | Serving packaging or its runtime contract changes |
| [Web serving evidence](evidence/demo-01-web-serving.md) | Compiled browser flows, same-origin API and dependency outage/recovery | Serving acceptance is verified |
| [Optional cache evidence](evidence/demo-01-optional-cache.md) | Explicit cache modes, readiness failures and Redis-free Compose verification | Cache mode or its dependency checks change |
| [ADR 0011: 3D and animated map](adr/0011-southbank-building-massing.md) | Accepted building source, MapLibre + deck.gl stack, animation classes and MAP-01–05 sequence | A MAP item or map context source changes |
| [MAP-02 input contract proposal](architecture/tram-animation-input-contract.md) | Transport prerequisites, continuous playback windows, receipt/shape semantics and API options | The architect reviews the proposal or MAP-02 implements it |
| [MAP-02 payload estimate](evidence/map-02-animation-payload.md) | Reproducible synthetic JSON/compression sizes and placement trade-offs | The proposed wire shape changes or real fixture measurements become available |
| [Google Cloud identity bootstrap](runbooks/gcp-bootstrap.md) | Terraform bootstrap for APIs, image repository, GitHub federation and the image builder | Bootstrap identities, trust conditions or apply steps change |
| [ADR 0012: managed demo resources](adr/0012-managed-demo-resource-profile.md) | Accepted database, connectivity, recovery, audience and worker profile | A later architect decision changes the profile |
| [Managed resource plan](architecture/demo-cloud-resource-plan.md) | Foundation ownership, connection envelope and deployment prerequisites | Resource/runtime controls or deployment gates change |
| [Foundation runbook](runbooks/demo-foundation.md) | Credential-free validation, reviewed plan/apply procedure and post-apply checks | Foundation operation or ownership changes |
| [Foundation evidence](evidence/demo-01-cloud-foundation.md) | Mocked resource/identity/recovery tests and their live-verification limits | A foundation acceptance boundary is verified |
| [Database initialization runbook](runbooks/demo-database.md) | SQL privilege matrix, private credential/extension setup and recovery procedure | Database privileges or initialization steps change |
| [Database initialization evidence](evidence/demo-01-database-bootstrap.md) | Actual foundation apply, managed PostGIS, SQL login caps and spatial compatibility | A managed database boundary is verified |
| [API pool evidence](evidence/demo-01-api-pool.md) | Shared API connection bound, saturation/recovery checks and deployment limits | API database lifecycle or verification changes |
| [Finite worker runbook](runbooks/city-job.md) | Manual target invocation, execution lock, deadline and recovery | Worker Job operation changes |
| [Finite worker evidence](evidence/demo-01-city-job.md) | Restricted-role completion, overlap, deadline and recovery results | Worker Job acceptance is verified |
| [Initialization Job runbook](runbooks/initialization-jobs.md) | Restricted migration/import commands, serialization, verification and recovery | Initialization Job behavior changes |
| [Initialization Job evidence](evidence/demo-01-initialization-jobs.md) | Real restricted-role migration/import acceptance and interruption checks | Initialization acceptance is verified |
| [Managed Jobs runbook](runbooks/managed-demo-jobs.md) | Definition inputs, plan/apply review and manual execution acceptance | Managed Job wiring or operations change |
| [Managed Jobs evidence](evidence/demo-01-managed-jobs.md) | Definition checks, first managed execution results and measurement limitations | Definition or managed-execution verification changes |
| [Image publishing](runbooks/image-publishing.md) | Main CI gate, federation configuration, immutable image records and failed-attempt recovery | Publishing workflow or record semantics change |
| [Image publishing evidence](evidence/demo-01-image-publishing.md) | Local container/registry verification and distinct live federation acceptance | A publication boundary is verified |
| [Compose cleanup evidence](evidence/compose-smoke-cleanup.md) | All-profile teardown, project isolation and absence of residual resources | Smoke lifecycle or cleanup checks change |
| [Phase 3 acceptance](evidence/phase-3-acceptance.md) | Durable reliability proof, operational demo and verified commit | Phase acceptance evidence or operational commands change |

| [Managed serving runbook](runbooks/managed-demo-serving.md) | IAP/sidecar inputs, private candidate deployment, promotion and rollback acceptance | Serving configuration or deployment procedure changes |
| [Managed serving evidence](evidence/demo-01-managed-serving.md) | Mocked topology/access/traffic tests and local runtime checks | A serving boundary is verified |

Use issues for scheduled work, ADRs for consequential technical choices, OpenAPI for implemented HTTP fields and dbt documentation for implemented models. Add runbooks alongside operational features. Keep technical documents focused on responsibilities and procedures; link to delivery status rather than repeating feature inventories.

Label fixture/live inputs and preserve the scope of dated evidence. The project brief uses revision numbers; software releases use version tags such as `v1.0.0`.

# Documentation

UrbanPulse is a Melbourne city intelligence project integrating transport, weather/hazards and planning/infrastructure. Maintain progress in the [delivery plan](delivery-plan.md); keep the README focused on the product and quickstart.

## Reading paths

For product review: [project brief](../project_brief.md) → [city MVP scenario](demos/city-mvp.md) → [delivery plan](delivery-plan.md).

For development: [repository guide](repository-guide.md) → [development guide](development.md) → [architecture](architecture/overview.md) → [testing strategy](testing-strategy.md) → the relevant decision/source record.

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

For the building layer: [MAP-01 walkthrough](demos/map-01.md) and [fixture/rendering evidence](evidence/map-01-building-massing.md).

For the animated 3D map: [ADR 0011](adr/0011-southbank-building-massing.md) → [MAP-02 input contract](architecture/tram-animation-input-contract.md) → [map context sources](source-register.md#map-context-sources).

For continuous deployment: [CD operations](runbooks/managed-demo-cd.md) and [managed delivery evidence](evidence/cd-01-managed-delivery.md).

For the public mixed-source view: [schedule sample walkthrough](demos/schedule-sample.md) and [ADR 0022](adr/0022-public-schedule-sample.md).

## Document responsibilities

| Document                                                 | Owns                                                               | Update when                                             |
| -------------------------------------------------------- | ------------------------------------------------------------------ | ------------------------------------------------------- |
| [ADR 0022](adr/0022-public-schedule-sample.md) | Mixed-source public sample, local Vicmap context, schedule semantics and Pages CSP | Source, sample or hosting rules change |
| [Schedule sample evidence](evidence/schedule-sample.md) | Source counts, sizes and static-browser verification | Sample dataset or rendering changes |
| [Schedule sample](demos/schedule-sample.md) | Offline builder and Pages deployment | Sample build or verification changes |
| [ADR 0020](adr/0020-synthetic-day-explorer.md) | Sole synthetic day UI, live-bounded history, fixed health/coverage panel and presentation boundaries | Preview time or data ownership changes |
| [GTFS archive Job](runbooks/gtfs-schedule-archive.md) | Bounded static download, retained-source inspection and immutable cloud publication | Job or deployment procedure changes |
| [GTFS archive evidence](evidence/gtfs-schedule-archive.md) | Integrity, change detection and offline retained-source verification | Validation or operational evidence changes |
| [Tram field audit](runbooks/tram-field-audit.md) | Read-only source-field census, bounds and schema-freeze evidence | Audit behavior or source field review changes |
| [Normalized Tram contract](architecture/normalized-tram-contract.md) | Accepted export isolation, stable keys and field-audit gate; range pins and alerts in 1c | Normalized schema or export semantics change |
| [GTFS Schedule archive](architecture/gtfs-schedule-archive.md) | Daily change-only static history proposal and least-privilege choice | Archive identity, source limits or IAM changes |
| [ADR 0021](adr/0021-independent-weather-planning-capture.md) | Cloud Weather/DAM Jobs and Scheduler: immutable GCS captures, prefix-only identities, snapshot consistency and daily-alert limits | Capture format, cloud scope, cadence or monitoring policy changes |
| [Synthetic day evidence](evidence/synthetic-day.md) | Browser/asset checks, rendering measurements and limitations | A changed preview is measured |
| [Synthetic day walkthrough](demos/synthetic-day.md) | Full-day visual demonstration and asset reproduction | Preview controls or assets change |
| [Repository guide](repository-guide.md) | Folder boundaries, explorer components and README screenshot | Code organization or screenshot workflow changes |
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
| [Raw tram activation evidence](evidence/cloud-01-raw-activation.md) | Dated service activation, store verification and cloud telemetry readback | A deployment or acceptance observation changes |
| [Weather/DAM bounded probe](evidence/src-02-weather-planning-probe.md) | Replayable public-source reads, response hashes and remaining enablement gates | Source access/schema measurements change |
| [Source register](source-register.md)                    | Provider evidence, coverage, access and open questions             | A source is evaluated, enabled or changes terms         |
| [Development guide](development.md)                      | Runnable setup, configuration and troubleshooting                  | Tooling or commands change                              |
| [Testing strategy](testing-strategy.md)                  | Existing checks and required feature coverage                      | Behavior or a service boundary changes                  |
| [Phase 0 demo](demos/phase-0.md)                         | Tagged phase-0 baseline walkthrough                                    | The current baseline changes                            |
| [Clean-checkout walkthrough](demos/clean-checkout.md)    | Isolated baseline reproduction and cleanup procedure               | Reproduction steps or the referenced checkpoint change  |
| [City MVP demo](demos/city-mvp.md)                       | Cross-domain acceptance scenario and evidence                      | Product acceptance rules are agreed or implemented      |
| [Local evidence](evidence/phase-0-local.md)              | Actual checks and their limits                                     | A new verification checkpoint is recorded               |
| [BASE-01 evidence](evidence/base-01-clean-checkout.md)   | Dated clean-checkout results, measurements and verification scope  | A new clean-checkout checkpoint is recorded             |
| [SRC-01 evidence](evidence/src-01-source-feasibility.md) | Official source findings, pilot comparison and reproduction method | Source evidence changes or a new comparison is measured |
| [SRC-02 transport evidence](evidence/src-02-transport-probe.md) | Bounded authentication, payload, freshness and exact GTFS-linkage measurements | New source samples or adapter assumptions change |
| [Transport probe runbook](runbooks/transport-source-probe.md) | Offline inspection, bounded live probe and private evidence handling | Probe limits, credentials or reproduction steps change |
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
| [ADR 0011: 3D and animated map](adr/0011-southbank-building-massing.md) | Accepted 6 October baseline and pre-MAP-02 glide; accepted 7 October MAP-02 clock, request and fallback amendments | A MAP item or map context source changes |
| [MAP-02 input contract](architecture/tram-animation-input-contract.md) | Accepted MAP-02 endpoint B, validity/polling, versioned clocks/identity, startup admission and receipt/shape semantics | Contract decisions or MAP-02 implementation change |
| [MAP-02 trip/shape foundation](evidence/map-02-trip-foundation.md) | Compatible trip metadata, pinned full GTFS shapes selected by area overlap and synthetic observations | Transport metadata or source fixture changes |
| [MAP-02 CBD expansion](evidence/map-02-cbd-expansion.md) | Second CLUE scope, shared full-route assets, source hashes and measured geometry growth | Area scope, fixture or expansion verification changes |
| [MAP-02 shape pool](evidence/map-02-shape-pool.md) | Order-independent per-shape build, immutable area references and cold/warm byte/request measurements | Shape packaging, manifest policy or serving verification changes |
| [MAP-02 chunk loading](evidence/map-02-chunk-loading.md) | Opt-in shape/route browser experiment, full-source overfetch and measured cold/warm cache behavior | Chunk selection or browser serving measurements change |
| [MAP-02 route validation](evidence/map-02-route-validation.md) | Gzip body sizes, browser-throttled loading and separately sampled V8 heap with raw reports | Transport encoding, route packaging or serving acceptance changes |
| [MAP-02 path interpolation](evidence/map-02-path-interpolation.md) | Pure two-observation distance interpolation, immutable prepared geometry and integration preconditions | Path interpolation or animation integration changes |
| [MAP-02 exact time](evidence/map-02-exact-time.md) | Strict UTC microsecond parsing, receipt eligibility, ceiling boundaries and safe interpolation conversion | Timestamp or window evaluation changes |
| [MAP-02 payload estimate](evidence/map-02-animation-payload.md) | Like-for-like encoding sizes, bounded per-vehicle fallback and recorded Python/zlib environment | The wire shape changes or real fixture measurements become available |
| [MAP-02 clock rollout](runbooks/map-02-clock-migration.md) | Normalizer coexistence, versioned fixtures/runs, revision-local input selection, managed cutover and pinned v1 recovery prerequisites | Clock migration or deployment compatibility changes |
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
| [ADR 0013](adr/0013-named-consumer-iap-access.md) | Accepted consumer-account OAuth and named operator access boundary | Audience or OAuth ownership changes through review |
| [Consumer IAP evidence](evidence/demo-01-consumer-iap.md) | Closed bootstrap and explicit-user mocked plan checks | OAuth/access validation is repeated |
| [Managed serving runbook](runbooks/managed-demo-serving.md) | IAP/sidecar inputs, private candidate deployment, promotion and rollback acceptance | Serving configuration or deployment procedure changes |
| [Managed serving evidence](evidence/demo-01-managed-serving.md) | Mocked topology/access/traffic tests, local runtime checks and managed bootstrap/read-back evidence | A serving boundary is verified |
| [ADR 0014](adr/0014-managed-demo-continuous-delivery.md) | Accepted remote-state and candidate/promotion direction; accepted MAP-02 import pins, staging and compatibility gates | Deployment ownership or security boundary changes |
| [Managed CD runbook](runbooks/managed-demo-cd.md) | Backend migration, workflow activation, private records and failure recovery | Delivery implementation or operating procedure changes |
| [Managed CD evidence](evidence/demo-01-continuous-delivery.md) | Offline guards, runner failure tests and activation limits | Deployment validation changes |
| [Tram collection policy](architecture/tram-collection-policy.md) | Accepted tram cadence, normalized history and attribution; raw duration separately proposed | Architect source-policy decision or new measurement |
| [ADR 0015](adr/0015-local-capture-collector.md) | Accepted operator-hosted collector, tiered retention and scoped upload key | Capture host, retention tiers or upload identity change |
| [CD operational evidence](evidence/cd-01-managed-delivery.md) | Exact publication, candidate and promotion runs, retained rollback and validation limits | A managed delivery milestone is verified |
| [MAP-01 walkthrough](demos/map-01.md) | 2D/3D controls, building scope and fallback | Map interactions change |
| [MAP-01 evidence](evidence/map-01-building-massing.md) | Building provenance, extrusion/packaging tests and rendering measurements | Fixture or renderer changes |
| [ADR 0016](adr/0016-local-capture-recovery.md) | Accepted local immutable capture journal and Linux recovery | Capture persistence or ownership changes |
| [Capture store v3](architecture/capture-store-v3.md) | Marker, bounded downstream records, expiry-aware verification and no-delete rollout | Capture persistence or recovery change |
| [V3 store evidence](evidence/cloud-01-v3-store.md) | Linux recovery, expiry provenance and persistent-volume runtime checks | v3 persistence or verification changes |
| [ADR 0018](adr/0018-capture-delivery-and-expiry.md) | Accepted v3 expiry mechanism; accepted B metadata confirmation and manual unlock | Capture expiry, downstream progress or IAM/unlock decision |
| [ADR 0017](adr/0017-incremental-capture-recovery.md) | Capture checkpoint, direct sequence index, downstream trade-offs, verification hold and fresh-store transition | Accepted incremental recovery contract; implementation and verification requirements |
| [ADR 0019](adr/0019-capture-infrastructure-and-monitoring.md) | Accepted telemetry identity amendment, operational metrics and enrollment gates | Collector cloud IAM or monitoring semantics change |
| [Capture infrastructure](runbooks/capture-infrastructure.md) | Independent Terraform root, private plans, IAM denial tests and monitoring enrollment | Landing or monitoring deployment changes |
| [Continuous collector](runbooks/collector-continuous.md) | Continuous scheduling, daemon recovery, capacity guards and heartbeat dry-run | Collector runtime or host recovery changes |
| [Encrypted collector host](runbooks/collector-encrypted-host.md) | Manual LUKS unlock, swap/reboot maintenance, guarded fixture service and locked-volume drill | Collector host/service configuration changes |
| [Local capture runbook](runbooks/local-capture.md) | Ubuntu fixture setup, recovery and bounded live gates | Collector operation or deployment changes |
| [Local capture evidence](evidence/cloud-01-local-capture.md) | Synthetic HTTP, filesystem and process-crash acceptance | Capture/recovery implementation changes |
| [Incremental capture evidence](evidence/cloud-01-incremental-recovery.md) | V2 checkpoint crash tests, read bounds and reproducible startup measurements | Recovery implementation or measurement changes |
| [Ubuntu capture rehearsal](evidence/cloud-01-ubuntu-acceptance.md) | Representative-host fixture recovery, reboot persistence and reproducible fault checks | Collector host or persistence acceptance changes |

Use issues for scheduled work, ADRs for consequential technical choices, OpenAPI for implemented HTTP fields and dbt documentation for implemented models. Add runbooks alongside operational features. Keep technical documents focused on responsibilities and procedures; link to delivery status rather than repeating feature inventories.

Label fixture/live inputs and preserve the scope of dated evidence. The project brief uses revision numbers; software releases use version tags such as `v1.0.0`.

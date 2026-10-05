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

## Document responsibilities

| Document                                                 | Owns                                                               | Update when                                             |
| -------------------------------------------------------- | ------------------------------------------------------------------ | ------------------------------------------------------- |
| [Project brief](../project_brief.md)                     | Product scope, selected technology and release requirements        | Product direction or a major constraint changes         |
| [Delivery plan](delivery-plan.md)                        | Milestones, dependencies and unresolved decisions                  | Scope, priority or completion evidence changes          |
| [Architecture](architecture/overview.md)                 | Domain ownership, contracts and data flow                          | A boundary, runtime or data path changes                |
| [ADR 0001](adr/0001-city-intelligence-scope.md)          | Accepted integrated product scope and consequences                 | A later decision supersedes it                          |
| [ADR 0002](adr/0002-southbank-tram-pilot.md)             | Accepted Southbank CLUE pilot and initial tram scope               | The architect changes the pilot or transport scope      |
| [ADR 0003](adr/0003-cloudevents-and-area-conditions.md) | Accepted CloudEvents format and separate condition/coverage principle | A later decision supersedes either principle |
| [ADR 0004](adr/0004-southbank-fixture-map.md) | Proposed fixture identity, point membership, local map and age policy | The architect accepts or revises the proposal |
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

Use issues for scheduled work, ADRs for consequential technical choices, OpenAPI for implemented HTTP fields and dbt documentation for implemented models. Add runbooks alongside operational features. Keep technical documents focused on responsibilities and procedures; link to delivery status rather than repeating feature inventories.

Label fixture/live inputs and preserve the scope of dated evidence. Document version is v1; record software release tags separately.

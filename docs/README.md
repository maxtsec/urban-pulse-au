# Documentation

UrbanPulse is a Melbourne city intelligence project integrating transport, weather/hazards and planning/infrastructure. Maintain progress only in the [README progress table](../README.md#progress) and [delivery plan](delivery-plan.md).

## Reading paths

For product review: [project brief](../project_brief.md) → [city MVP scenario](demos/city-mvp.md) → [delivery plan](delivery-plan.md).

For development: [development guide](development.md) → [architecture](architecture/overview.md) → [testing strategy](testing-strategy.md) → the relevant decision/source record.

For local setup demonstration: [Phase 0 walkthrough](demos/phase-0.md) and [local evidence](evidence/phase-0-local.md).

## Document responsibilities

| Document                                        | Owns                                                        | Update when                                        |
| ----------------------------------------------- | ----------------------------------------------------------- | -------------------------------------------------- |
| [Project brief](../project_brief.md)            | Product scope, selected technology and release requirements | Product direction or a major constraint changes    |
| [Delivery plan](delivery-plan.md)               | Milestones, dependencies and unresolved decisions           | Scope, priority or completion evidence changes     |
| [Architecture](architecture/overview.md)        | Domain ownership, contracts and data flow                   | A boundary, runtime or data path changes           |
| [ADR 0001](adr/0001-city-intelligence-scope.md) | Accepted integrated product scope and consequences          | A later decision supersedes it                     |
| [Source register](source-register.md)           | Provider evidence, coverage, access and open questions      | A source is evaluated, enabled or changes terms    |
| [Development guide](development.md)             | Runnable setup, configuration and troubleshooting           | Tooling or commands change                         |
| [Testing strategy](testing-strategy.md)         | Existing checks and required feature coverage               | Behavior or a service boundary changes             |
| [Phase 0 demo](demos/phase-0.md)                | Present-day fixture walkthrough                             | The current baseline changes                       |
| [City MVP demo](demos/city-mvp.md)              | Cross-domain acceptance scenario and evidence               | Product acceptance rules are agreed or implemented |
| [Local evidence](evidence/phase-0-local.md)     | Actual checks and their limits                              | A new verification checkpoint is recorded          |

Use issues for scheduled work, ADRs for consequential technical choices, OpenAPI for implemented HTTP fields and dbt documentation for implemented models. Add runbooks alongside operational features. Keep technical documents focused on responsibilities and procedures; link to delivery status rather than repeating feature inventories.

Label fixture/live inputs and preserve the scope of dated evidence. Document version is v1; record software release tags separately.

# UrbanPulse AU

**What is happening around my city right now, and how healthy is an area?**

![UrbanPulse Melbourne: a 3D city map, timetable-simulated trams and area conditions](docs/images/urbanpulse-app.jpg)

Explore Melbourne CBD and Southbank through transport, weather and development activity. Switch between 2D and 3D, replay a day, and see what explains an area's condition.

The sample combines real buildings, streets, tram schedules and development records with **simulated tram movement, scripted incidents and synthetic weather**. It is not a live service-status map. [Sources and attribution](sample-data/README.md).

## What is real today

- **Continuous real Tram capture:** positions, trip updates and alerts collected on a dedicated encrypted host, with Cloud Monitoring heartbeat, feed-health and capacity alerts. [Activation and notification evidence](docs/evidence/cloud-01-raw-activation.md).
- **Terraform-managed GCP:** Cloud Run serving and Cloud SQL/PostGIS, with separate runtime identities and bounded database access. [Database deployment](docs/evidence/demo-01-database-bootstrap.md) · [Deployed serving revision](docs/evidence/cd-01-managed-delivery.md#executions).
- **Protected continuous delivery:** federated GitHub authentication, automatic zero-traffic candidates, operator-approved promotion and retained rollback targets. [CD execution evidence](docs/evidence/cd-01-managed-delivery.md).

These are running collection and deployed demo systems; the public sample remains separate from collected realtime data.

## Try it locally

With Node.js 24 and npm, run from the repository root:

```sh
npm --prefix apps/web ci
npm --prefix apps/web run dev
```

Open **http://127.0.0.1:5173/**. The sample runs without a backend or API keys. Start with **Day overview**, jump to a busy period, then compare CBD and Southbank.

## Architecture

System design across collection, analytics, application serving and the standalone sample:

```mermaid
flowchart TB
    subgraph Collection["Source collection"]
        Tram["Tram GTFS-Realtime"] --> Raw["Encrypted local store<br/>Payloads · receipts · manifests"]
        Raw --> Normalize["Local normalization<br/>Stable record keys · Parquet"]
        Public["Weather · DAM · GTFS Schedule"] --> Jobs["Cloud Run capture Jobs"]
        Scheduler["Cloud Scheduler"] --> Jobs
        Raw --> Monitoring["Cloud Monitoring<br/>Heartbeat · feed health · capacity"]
    end

    subgraph Analytics["Historical data pipeline"]
        Landing["GCS landing<br/>Source / date partitions"] --> Process["Dagster jobs + Polars<br/>Partitions · reruns · backfill"]
        Process --> BQ["BigQuery staging"]
        BQ --> Dbt["dbt<br/>stg → int → marts · data tests"]
        Dbt --> Publish["Validated serving publication"]
    end
    Normalize -->|Normalized Tram only| Landing
    Jobs -->|Source responses and schedule archives| Landing

    subgraph Backend["Application and serving"]
        Fixture["Fixture imports"] --> Domains["Transport · Weather · Planning"]
        Domains --> Events["Postgres outbox + consumer ledger<br/>Idempotency · retry · dead-letter / replay"]
        Events --> Location["Location Intelligence<br/>Spatial rules · status · coverage"]
        Location --> DB["Cloud SQL / PostGIS<br/>Domain history · serving data"]
        DB --> API["FastAPI + web on Cloud Run<br/>IAP-protected map and area queries"]
    end
    Publish --> DB

    subgraph Delivery["Infrastructure and delivery"]
        CI["GitHub Actions<br/>Tests · OIDC federation"] --> Images["Artifact Registry<br/>Images pinned by digest"]
        Images --> Deploy["Terraform / CD<br/>Zero-traffic candidate · approved promotion"]
        Deploy --> API
    end

    subgraph Sample["Standalone public sample"]
        Pinned["Pinned public datasets<br/>GTFS · buildings · DAM · streets / river"] --> Builder["Reproducible sample builder<br/>Source hashes · manifest · attribution"]
        Builder --> Web["Static React + MapLibre / deck.gl<br/>Timetable simulation · authored conditions"]
    end

    classDef storage fill:#eef2f6,stroke:#64748b,color:#172b3a
    classDef application fill:#e9f5f2,stroke:#45877a,color:#163d34
    classDef operations fill:#fff5e5,stroke:#aa7e34,color:#58421d
    class Raw,Landing,BQ,DB,Images storage
    class Domains,Location,API,Web application
    class Monitoring,CI,Deploy operations
```

Tram raw stays on the encrypted host; only normalized Tram records enter cloud landing. The static sample uses its own versioned assets. Collection, analytical processing and API requests have separate execution paths. [Architecture and domain boundaries](docs/architecture/overview.md) · [Tests and evidence](docs/testing-strategy.md) · [Delivery plan](docs/delivery-plan.md)

## Repository guide

```text
apps/          FastAPI entry points and React web app
urbanpulse/    Domain rules, use cases, contracts and adapters
workers/       Capture, ingestion and event-processing entry points
pipelines/     Data pipeline workspace
migrations/    Versioned database changes
infra/         Terraform roots
ops/           Host and service configuration
scripts/       Builders, checks and operator tools
sample-data/   Pinned sample sources and attribution
tests/         Python unit and integration tests
docs/          Architecture decisions, demos and evidence
```

[Folder responsibilities](docs/repository-guide.md) · [Backend setup](docs/development.md) · [Sample walkthrough](docs/demos/schedule-sample.md) · [Documentation](docs/README.md)

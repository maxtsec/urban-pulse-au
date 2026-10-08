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

## Target architecture

Solid arrows show data and query paths; dashed arrows show deployment and scheduling.

```mermaid
flowchart TB
    subgraph Sources["City data sources"]
        Tram["Tram GTFS-Realtime"]
        Weather["Open-Meteo weather"]
        DAM["DAM developments"]
        GTFS["GTFS Schedule"]
        Context["Buildings · streets · river"]
    end

    subgraph Collection["Capture and source history"]
        Raw["Encrypted local Tram store<br/>Payloads · receipts · manifests"]
        Normalize["Local normalization<br/>Stable record keys · Parquet"]
        Jobs["Weather / DAM<br/>Cloud Run capture Jobs"]
        Archive["GTFS Schedule archive Job<br/>Daily check · version on change"]
        Scheduler["Cloud Scheduler"]
        Monitoring["Cloud Monitoring<br/>Heartbeat · last success · capacity"]
    end
    Tram --> Raw --> Normalize
    Weather --> Jobs
    DAM --> Jobs
    GTFS --> Archive
    Scheduler -.->|15 min weather / daily DAM| Jobs
    Scheduler -.->|Daily| Archive
    Raw -->|Capture and capacity metrics| Monitoring
    Jobs -->|Execution and success metrics| Monitoring
    Archive -->|Execution and success metrics| Monitoring

    subgraph Analytics["Historical data pipeline"]
        Landing["GCS landing<br/>Source / date partitions"]
        Process["Dagster on Cloud Run Jobs + Polars<br/>Partitions · reruns · backfill"]
        Warehouse["BigQuery + dbt<br/>staging → intermediate → marts<br/>Data tests · scan accounting"]
        Publish["Validated serving publication"]
        Landing --> Process --> Warehouse --> Publish
    end
    Normalize -->|Normalized Tram only| Landing
    Jobs -->|Raw responses and manifests| Landing
    Archive -->|Tram schedule member and provenance| Landing
    Scheduler -.->|Partition execution| Process

    subgraph Serving["Application and area intelligence"]
        Worker["Domain / Location workers<br/>Outbox · consumer ledger<br/>Idempotency · retry · replay"]
        DB["Cloud SQL / PostGIS<br/>Domain history · area summaries"]
        API["FastAPI + web on Cloud Run"]
        IAP["IAP<br/>Authenticated access"]
        City["Protected city map and area panels"]
        Worker <-->|Events and projections| DB
        DB <-->|Spatial and time queries| API
        API <--> IAP <--> City
    end
    Publish --> DB

    subgraph Sample["Standalone public sample"]
        Builder["Reproducible sample builder<br/>Pinned sources · hashes · attribution"]
        Pages["GitHub Pages<br/>React · MapLibre · deck.gl<br/>Schedule simulation · authored conditions"]
        Builder -->|Versioned sample assets| Pages
    end
    GTFS -->|Pinned timetable and shapes| Builder
    DAM -->|Dated project snapshot| Builder
    Context --> Builder

    subgraph Delivery["Infrastructure and delivery"]
        CI["GitHub Actions<br/>Tests · OIDC federation"]
        Images["Artifact Registry<br/>Images pinned by digest"]
        Deploy["Terraform / CD<br/>Zero-traffic candidate<br/>Approved promotion · rollback"]
        CI -.->|Publish images| Images
        Images -.->|Select immutable release| Deploy
        Deploy -.->|Deploy| API
        Deploy -.->|Configure Jobs| Jobs
        Deploy -.->|Configure archive Job| Archive
        CI -.->|Manual Pages deployment| Pages
    end

    classDef storage fill:#eef2f6,stroke:#64748b,color:#172b3a
    classDef application fill:#e9f5f2,stroke:#45877a,color:#163d34
    classDef operations fill:#fff5e5,stroke:#aa7e34,color:#58421d
    class Raw,Landing,Warehouse,DB,Images storage
    class Worker,API,IAP,City,Pages application
    class Monitoring,Scheduler,CI,Deploy operations
```

Tram raw stays on the encrypted host; only normalized Tram records enter cloud landing. Shared public sources also feed the independently built sample; GitHub Pages does not call the protected API. [Architecture and domain boundaries](docs/architecture/overview.md) · [Tests and evidence](docs/testing-strategy.md) · [Delivery plan](docs/delivery-plan.md)

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

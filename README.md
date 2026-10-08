# UrbanPulse AU

**What is happening around my city right now, and how healthy is an area?**

![UrbanPulse Melbourne: a 3D city map, timetable-simulated trams and area conditions](docs/images/urbanpulse-app.jpg)

Explore Melbourne CBD and Southbank through transport, weather and development activity. Switch between 2D and 3D, replay a day, and see what explains an area's condition.

The sample combines real buildings, streets, tram schedules and development records with **simulated tram movement, scripted incidents and synthetic weather**. It is not a live service-status map. [Sources and attribution](sample-data/README.md).

## Try it locally

With Node.js 24 and npm, run from the repository root:

```sh
npm --prefix apps/web ci
npm --prefix apps/web run dev
```

Open **http://127.0.0.1:5173/**. The sample runs without a backend or API keys. Start with **Day overview**, jump to a busy period, then compare CBD and Southbank.

## Behind the map

- **Frontend:** React, TypeScript, MapLibre and deck.gl, with reproducible, source-labelled sample data.
- **Backend:** FastAPI and PostgreSQL/PostGIS, separated into domain rules, application use cases and adapters.
- **Reliability:** durable event delivery, idempotent processing, recovery tools and integration tests.
- **Operations:** Terraform, Cloud Run, protected delivery and monitored local Tram capture.

The real-data warehouse pipeline is in development; the sample does not present its simulated results as measured analytics. [Architecture](docs/architecture/overview.md) · [Tests and evidence](docs/testing-strategy.md) · [Delivery plan](docs/delivery-plan.md)

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

# Repository guide

Start with the [README](../README.md) to run the sample, or the [development guide](development.md) for the API and database. Delivery status belongs in the [delivery plan](delivery-plan.md).

## Application boundaries

| Folder | Responsibility |
| --- | --- |
| `apps/api/` | HTTP routes and startup configuration; delegate business work to application use cases |
| `apps/web/src/explorer/` | Public sample experience, playback, schedule calculation and demo conditions |
| `apps/web/src/animation/` | Exact timestamp and path-interpolation helpers |
| `apps/web/src/assets/` | Local map context, models and generated sample assets |
| `apps/web/tests-pages/` | Static sample browser behaviour, including subpath hosting and lazy history |
| `apps/web/tests/`, `apps/web/unit/` | API-backed browser scenarios and frontend unit tests |
| `urbanpulse/` | Transport, weather, planning and location rules, contracts, application coordination and adapters |
| `workers/` | Independently runnable capture, ingestion and event work |
| `pipelines/` | Pipeline workspace; see the delivery plan for implemented versus planned work |
| `migrations/` | Ordered database schema changes |
| `infra/`, `ops/` | Cloud resources and host/service definitions |
| `scripts/`, `tests/` | Reproducible builders, operator checks and Python tests |
| `sample-data/` | Source archive, hash lock and licensing notes, separate from the website build |
| `docs/` | Decisions, source register, runbooks, walkthroughs and evidence |

Dependencies flow from entry points to application use cases and domain rules. Adapters handle external systems. Keep UI sample conditions separate from production area-status semantics; sample trams are scheduled trips, not observed vehicles.

## Explorer structure

```text
explorer/
  SampleExplorer.tsx       Load and verify the sample
  Explorer.tsx             Coordinate map, selected area and panels
  components/
    DayPlayer.tsx          Playback controls; consumes the shared clock
    InformationTabs.tsx    Accessible panel navigation
    SourceCredits.tsx      Dataset attribution
  useDayPlayback.ts        Single owner of playback, seeking and live edge
  schedule.ts              Timetable positions along retained GTFS shapes
  sample.ts                Manifest checks and lazy previous-day loading
  health-demo.ts           Explicitly authored demo conditions
  HealthPanel.tsx          Condition, reasons and affected-trip share
  DayOverview.tsx          Day summary and navigation
  scene.ts                 Illustrative 3D objects
```

`CityMap.tsx` is shared with the fixture harness. `App.tsx` and the original scenario components remain for API integration tests; they are not a second public UI. This refactor extracts presentation components without moving the playback state, changing source data or altering API contracts.

## README screenshot

The image is a browser capture of the actual app, including the scripted-status notice. No statistics or map objects are added after capture.

From `apps/web`, build and start a preview:

```sh
npm run build -- --base=/urban-pulse-au/
npm run preview -- --port 5182 --base=/urban-pulse-au/
```

In another terminal in the same folder:

```sh
node scripts/capture-readme.mjs
```

Install Playwright Chromium with `npm run test:e2e:install` if needed. The script opens the sample in normal-motion mode, paused at 09:15 in 3D, waits for buildings/models, zooms in once, and writes `docs/images/urbanpulse-app.jpg`. It checks that Play is enabled and the reduced-motion notice is absent. Review it after map or layout changes. Run `npx playwright test --config=playwright.pages.config.ts` with the preview stopped to verify the sample's full browser flows.

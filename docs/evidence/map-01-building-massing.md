# MAP-01 building massing evidence

Recorded 7 October 2026. Scope and rules: [ADR 0011](../adr/0011-southbank-building-massing.md). Walkthrough: [MAP-01](../demos/map-01.md). Delivery status belongs in the [delivery plan](../delivery-plan.md).

## Provenance and geometry

The [City of Melbourne dataset](https://data.melbourne.vic.gov.au/explore/dataset/2023-building-footprints/) and its catalogue API were rechecked: CC BY 4.0. The boundary-intersection export contains 1,189 polygons. The retained layer has 1,108 Structure polygons across 320 structures. Excluded: 34 Tram Stops, 30 Bridges, 15 Jetties, one Toilet and one Tunnel. No Structure elevation/coordinate rejection occurred.

Included capture dates: 850 polygons from 2018-05-28, two from 2020-05-15, 161 from 2022-01-20 and 95 from 2023-05-11. These are the filtered counts; ADR 0011's 1,189-polygon date table covers all types.

The [manifest](../../tests/fixtures/southbank-buildings.manifest.json) records the export endpoint/query, retrieval date, source response SHA-256, retained boundary SHA-256, fixture SHA-256, counts and changes. The [generator](../../scripts/build_building_fixture.py) produces deterministic sorted compact GeoJSON, rounds coordinates to six decimals and records rejections rather than substituting heights. Original source bytes are retained locally, not included in the image.

A component's vertices carry `base_m = footprint_min_elevation - structure_min_elevation`; deck.gl adds only `top_m - base_m`. This preserves stacked podium/tower offsets. Holes and MultiPolygon parts are retained. PostGIS independently checks validity and Southbank intersection for every rounded polygon. No clipping, geometry simplification, default heights or domain inputs are introduced.

To reproduce from a retained export obtained with the manifest's exact query:

```powershell
uv run --locked python -m scripts.build_building_fixture --source .local/map-01-source/source.geojson --retrieved-on 2026-10-07
uv run --locked pytest tests/unit/test_building_fixture.py -q
uv run --locked pytest -m integration tests/integration/test_building_postgis.py -q
```

Do not feed an unfiltered city-wide export to this generator. A refresh must repeat source/query/licence checks, spatial verification and manifest review. The generated GeoJSON is exempt from Prettier because its exact canonical bytes are hashed; no other source files are exempted.

## Rendering and packaging

Pinned deck.gl 9.4.0 uses its MapLibre-specific interleaved overlay, sharing MapLibre's camera and WebGL2 context. The building module and hashed GeoJSON are lazy-loaded from the application origin only after 3D is requested. Toggling off aborts pending attachment and removes GPU resources; retaining the parsed static data avoids repeated downloads. Camera changes do not recreate the map or update API queries. Readiness is reported after the overlay's first rendered frame, with a separate asset/rendering failure message.

Both new source paths are explicit entries in the web Docker context allowlist. The fixture is 795,145 bytes uncompressed (79,786 bytes gzip). The building entry chunk is approximately 689 kB (192 kB gzip), with additional lazily resolved renderer chunks; it is not part of the initial 2D download. Vite still reports chunks over 500 kB; lazy loading controls when they are requested, not their total size. There is no CDN, remote font, model asset or basemap request.

## Validation and measurement

Automated coverage includes valid relative heights, invalid/missing/non-finite elevation rejection, coordinate rounding, type exclusion, deterministic output, manifest/hash agreement and retained boundary identity. Browser cases cover default 2D without a building request, 3D/layer toggles, no extra domain requests, map/list selection, unchanged area condition, attribution, local-only requests, failed-asset retry and mobile reduced-motion layout. Desktop and mobile screenshots were visually inspected.

Run regression checks with `npm --prefix apps/web run test:e2e`. Rendering measurements are opt-in diagnostics, skipped in normal CI and serving smoke. In PowerShell set `$env:URBANPULSE_MEASURE_BUILDINGS="1"`, run `npm --prefix apps/web run test:e2e -- building-performance.spec.ts`, then remove the flag with `Remove-Item Env:URBANPULSE_MEASURE_BUILDINGS`. The same flag enables measurements with `playwright.serving.config.ts`; both profiles inherit that configuration's base URL. The two cases attach measurements and screenshots. Measurements use a two-second requestAnimationFrame sample during right-drag camera input. The JSON includes browser/renderer identity, 3D readiness latency and CDP JavaScript heap before/after. RAF cadence is not GPU frame-completion rate, and JavaScript heap excludes GPU/process memory. Mobile is Chromium emulation, not a physical device; software-rendered results cannot certify smooth animation on target hardware.

The recorded Chromium 153.0.8010.12 run used ANGLE SwiftShader (Vulkan software rendering):

| Profile | 3D ready | JS heap before / after | RAF cadence | p95 frame gap |
| --- | --- | --- | --- | --- |
| desktop | 1426 ms | 8.2 / 21.5 MiB | 9.1 Hz | 533.3 ms |
| mobile | 1670 ms | 7.1 / 16.1 MiB | 7.0 Hz | 550.0 ms |

Desktop: 1440×1100 at device scale 1. Mobile: 390×844 at scale 2 with touch/mobile emulation. These are single-run diagnostics, not stable performance budgets. Software-rendered camera movement is visibly limited; this does not establish smooth target-device animation. No geometry was simplified solely to improve a software-renderer score. Keep 2D as the default and review real-device performance before claiming broader 3D performance acceptance.

Checks: 600 unit tests, the real PostGIS building test, Ruff lint/format, mypy, ESLint/Prettier, production TypeScript/Vite build, and both actual/adversarial Docker build inventories passed. Initial verification passed the full 56-case browser suite and five targeted building cases. Review follow-up passed the compiled Caddy serving smoke with 65 browser cases, explicitly enabling both rendering diagnostics on the dynamically allocated serving origin, followed by API/database outage recovery and resource cleanup. Final camera-preservation and 2D-only glide refinements passed 13 affected browser cases; both opt-in measurement cases were skipped by default. On context loss, markers are removed and the accessible city list remains usable. Context restoration recreates the map and building overlay at the retained camera, using the latest clock, selection and layer state.

References: [interleaved overlay](https://deck.gl/docs/api-reference/maplibre/overview), [polygon extrusion](https://deck.gl/docs/api-reference/layers/polygon-layer), [source register](../source-register.md#map-context-sources).

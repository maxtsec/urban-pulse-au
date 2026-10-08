# Synthetic day visual checks

Measured 2026-10-08 against the compiled feature working tree, with Playwright Chromium and software WebGL (SwiftShader). Local results describe a preview, not hosted or hardware-GPU acceptance. Progress is recorded in the [delivery plan](../delivery-plan.md).

## Functional checks

- Full pre-existing and initial preview browser suite: 63 passed, 2 opt-in building measurements skipped. An expanded preview-only run then passed all 6 tests, including CSP, failed models, missing buildings and WebGL restoration.
- 26 typed frontend unit tests passed, including 5 day-fixture tests. Seek is stateless, all twelve windows cover the day, sample receipts never require future input, authored weather transitions are explicit and copied boundary provenance matches the retained source.
- Web lint, formatting and build passed. Ruff lint/format passed. Real Docker web build smoke under `python -O` passed both complete source inventories and static asset export. No changes to cloud resources, databases or provider adapters are part of this preview.
- Desktop 1440 x 1000 and mobile 390 x 844 layouts were visually inspected. Models have coloured highlights and minimum pixel sizes; missing assets preserve the accessible list and flat markers. All rendering requests stay on the application origin under the deployed CSP.

## Rendering sample

Five-second rainy playback, 30x, six simulated trams, three illustrative sites and historical buildings. The clock requests at most 30 UI updates per second. RAF measures browser callback scheduling, not unique presented GPU frames. These samples expose slow software rendering and **do not establish smooth playback on a user's GPU**; 2D remains the default.

| View | RAF callbacks/s | p95 RAF interval | JS heap after GC |
| --- | ---: | ---: | ---: |
| desktop 1440 x 1000 | 7.5 | 283.3 ms | 17.1 MiB |
| mobile 390 x 844 | 8.1 | 249.9 ms | 16.6 MiB |

The cold resource sample totals about 1.60 MiB encoded bodies including the map worker and building geometry. The three local model files total 8,040 bytes. The scene renderer is loaded only when opting into 3D; the synthetic day UI is separately lazy-loaded. The existing large map/overlay bundle warning remains. A deployment decision should include a real-browser GPU performance check; these software-rendered figures are not a performance pass.

Reproduce from the repository root after `npm --prefix apps/web run build`. In another terminal start `npm --prefix apps/web run preview -- --port 5178`, then run `node scripts/measure_synthetic_day.mjs`. Results and screenshots go to ignored `.local/synthetic-day/`. An existing loopback serving smoke URL may be supplied through `URBANPULSE_SERVING_URL`. Run without other builds/tests for comparison; frame timing is environment-dependent.

## Dependency limitation

`@deck.gl/mesh-layers` is pinned to the existing deck.gl version, 9.4.0. Its glTF loaders bring Node-side texture-compression tooling: npm audit reports eight affected package entries stemming from [image-size ICNS parsing](https://github.com/advisories/GHSA-w3rx-r6r6-pgpr) and [sprintf-js precision parsing](https://github.com/advisories/GHSA-hp3w-g68c-fv3c). The suggested automated fix downgrades deck.gl across a major version; it was not applied. This preview loads only checked-in original untextured models, does not accept uploaded images, and the serving image contains no Node toolchain. This bounds the exposed path but is not a claim that the dependency advisories are fixed. Recheck with `npm audit` before broadening asset input.

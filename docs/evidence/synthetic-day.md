# Synthetic day visual checks

Measured 2026-10-08 against the compiled feature working tree, with Playwright Chromium and software WebGL (SwiftShader). Local results describe a preview, not hosted or hardware-GPU acceptance. Progress is recorded in the [delivery plan](../delivery-plan.md).

## Functional checks

- The complete browser run passed 72 checks: 59 retained scenario checks and 13 explorer checks, with 2 opt-in building measurements skipped. Regressions cover seeking to 10:20 after Live reaches 10:30, 3D readiness on re-entry, and resizing across the 900px breakpoint, alongside fixed panels, keyboard tabs, model zoom growth, CSP, asset failure and WebGL recovery.
- 29 typed frontend unit tests passed. Interpolation tests change each endpoint independently, including reverse travel and startup holds. Seek is stateless, samples never require future receipt, live bounds are explicit and original model files require no compression extensions.
- Web lint, formatting and production build passed. Real Docker context/export verification and 19 compiled Caddy browser checks passed, including API/database outage and recovery; no cloud resources, database semantics or provider adapters change in this UI PR.
- Desktop and mobile layouts were visually inspected. Models use fixed world-space scale (tram 3×, works 1.5×), without pixel clamps. A rendered browser regression compares connected coloured model regions before and after zoom, excluding UI legends. Missing assets preserve the accessible list and flat markers.
- The production entry always renders the full-day explorer. `npm run build:test` emits a separate `dist-test` harness for retained scenarios; ordinary builds and the Docker allowlist exclude test entry files. Health displays status and synthetic coverage, without a numeric score.
- The glTF loader imports meshopt eagerly even for uncompressed models. A scoped build alias reports that decoder unsupported and rejects decode calls, avoiding unwanted WASM initialization under the existing CSP. The three original model assets have no required or used compression extensions.

## Rendering sample

Final fixed-panel working tree based on `5ce4322`, recorded dirty on 2026-10-08: five-second rainy playback, 30x, six simulated trams, three illustrative sites and historical buildings. The clock requests at most 30 UI updates per second. RAF measures browser callback scheduling, not unique presented GPU frames. Software rendering **does not establish smooth playback on a user's GPU**; 2D remains the default.

| View | RAF callbacks/s | p95 RAF interval | JS heap after GC |
| --- | ---: | ---: | ---: |
| desktop 1440 x 1000 | 7.6 | 266.7 ms | 16.9 MiB |
| mobile 390 x 844 | 8.6 | 250.0 ms | 16.6 MiB |

The cold resource sample totals 1,652,654 encoded bytes including the map worker and building geometry. The three local model files total 8,040 bytes. Both scenes reported models ready. The scene renderer is loaded only when opting into 3D; the synthetic day UI is separately lazy-loaded. The existing large map/overlay bundle warning remains. A deployment decision should include a real-browser GPU performance check; these software-rendered figures are not a performance pass.

Reproduce from the repository root after `npm --prefix apps/web run build`. In another terminal start `npm --prefix apps/web run preview -- --port 5178`, then run `node scripts/measure_synthetic_day.mjs`. Results and screenshots go to ignored `.local/synthetic-day/`. An existing loopback serving smoke URL may be supplied through `URBANPULSE_SERVING_URL`. Run without other builds/tests for comparison; frame timing is environment-dependent.

## Dependency limitation

`@deck.gl/mesh-layers` is pinned to the existing deck.gl version, 9.4.0. Its glTF loaders bring Node-side texture-compression tooling: npm audit reports eight affected package entries stemming from [image-size ICNS parsing](https://github.com/advisories/GHSA-w3rx-r6r6-pgpr) and [sprintf-js precision parsing](https://github.com/advisories/GHSA-hp3w-g68c-fv3c). The suggested automated fix downgrades deck.gl across a major version; it was not applied. This preview loads only checked-in original untextured models, does not accept uploaded images, and the serving image contains no Node toolchain. This bounds the exposed path but is not a claim that the dependency advisories are fixed. Recheck with `npm audit` before broadening asset input.

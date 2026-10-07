# MAP-02: per-shape versus per-route loading experiment

An opt-in Chromium experiment compares the [per-shape baseline](map-02-shape-pool.md) with one complete route per object. Both use the retained tram member, content-addressed objects and independent area manifests. This supplies evidence for a later serving choice; it does not select a production chunk policy or install a runtime loader.

## Inputs and method

The builder reads the pinned statewide archive and verifies its tram member hash using the [foundation source pins](map-02-trip-foundation.md). All 535 source shapes are measured with the existing PostGIS distance calculation. Their 371 pilot-union shapes must reproduce the retained features byte for byte. Route objects include **all** shapes referenced by that route's static trips, including shapes outside either area and all timetable service variants; no active-service-day filter is applied. Filtering the input to the pilot union would understate route overfetch.

Route objects exclude source release metadata, just like the baseline. Manifests keep tram-member revision, statewide provenance, attribution and the area's exact required shape IDs. A shape used by multiple routes appears in each corresponding object; transferred duplicate bytes count, and the browser checks that duplicate geometry agrees before selecting only the area's shapes. Area order and adding a third area do not rename existing objects or manifests. A changed shape invalidates its containing route objects, a coarser cache unit than the per-shape baseline.

The [build report](../../tests/fixtures/map02-expansion/chunk-comparison-report.json) records exact manifests and sizes. The [browser report](../../tests/fixtures/map02-expansion/chunk-browser-report.json) records all 48 loads, source commit, clean/dirty flag, source-file hashes and input-report hash. The measured code is commit `059a42e53a076e23ed6bb8dd9628db5ceac4c6eb`, with a clean worktree, Node 24.19.0 and Chromium 153.0.8010.12. These identify the experiment, not collector host details.

Each policy runs both area orders three times, with a fresh browser context for each pair. The second area uses that context's real HTTP cache. The local HTTP/1.1 server sends immutable cache headers; its request log counts actual network bodies, excluding the harness document. Every manifest and object is checked for SHA-256 and byte length before parsing. At most six geometry fetches run concurrently. This is an isolated asset experiment, not a change to the animation contract's one-request API concurrency.

Two profiles apply either zero or 50 ms of synthetic server delay to each network asset response, with no compression or bandwidth throttle. The latter is a sensitivity experiment, **not measured IAP latency or a network RTT model**. Wall time includes fetch, integrity checks, UTF-8 decoding/JSON parsing, route deduplication and hashing the selected geometry. Summed asynchronous hash time is not CPU time. All loads produced the same selected-geometry digest for each area across both layouts and cache states.

## Results

Network requests include the area manifest. Bytes are exact uncompressed response bodies. Time columns are the median of three wall-time measurements, in milliseconds.

| Area / cache | Layout | Requests | Bytes | Extra unique shapes | No added delay | 50 ms per response |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Southbank cold | Shape | 209 | 2,617,143 | 0 | 154.9 | 2,317.9 |
| Southbank cold | Route | 13 | 3,212,510 | 126 | 56.1 | 226.2 |
| CBD cold | Shape | 367 | 4,227,364 | 0 | 231.1 | 3,967.5 |
| CBD cold | Route | 23 | 4,991,612 | 153 | 81.1 | 351.6 |
| CBD after Southbank | Shape | 164 | 1,701,212 | 0 | 186.1 | 1,856.0 |
| CBD after Southbank | Route | 11 | 1,786,120 | 153 | 63.1 | 226.3 |
| Southbank after CBD | Shape | 6 | 90,991 | 0 | 91.3 | 191.4 |
| Southbank after CBD | Route | 1 | 7,018 | 126 | 47.6 | 96.6 |

For this release, route grouping cuts cold requests by about 94% while adding about 23% Southbank bytes and 18% CBD bytes relative to the current per-shape envelopes/manifests. These exact encodings differ from an informal route-collection estimate. Warm-route Southbank only fetches its manifest because CBD already fetched every required route object. Cached objects are still read, verified and parsed; no in-memory decoded-object cache is assumed.

This supports testing route grouping as a latency-sensitive candidate. It does not establish the best production policy: compression, HTTP/2, constrained bandwidth, memory/GC, mobile hardware, partial failures, real IAP serving and map rendering/FPS remain unmeasured. The fixed execution order and three samples are useful for comparison, not statistical performance acceptance. Route mutation also replaces more geometry per changed shape. Production grouping, limits and fallback remain an architect decision before serving.

## Reproduce

Start local PostGIS and install the locked Python and web dependencies plus Playwright Chromium using the normal development setup. Supply the retained official archive locally; do not commit it. Both archive hashes must match the source pins. From the repository root:

```bash
uv run python -m scripts.build_tram_chunk_comparison --archive .local/map-02-source/gtfs.zip --output .local/chunk-comparison
node scripts/benchmark_tram_chunks.mjs --assets .local/chunk-comparison --output .local/chunk-browser.json
uv run pytest -q tests/unit/test_tram_chunk_comparison.py
uv run pytest -m integration -q tests/integration/test_tram_shapes.py
```

In an isolated worktree, `--web-root <checkout>/apps/web` may reuse that checkout's installed locked Playwright package; use the same lockfile. The builder uses a read-only database transaction. The benchmark listens only on loopback, serves only generated hash-named JSON assets and closes the browser/server after completion or failure. It does not use provider credentials or contact live feeds. Assets and intermediate reports stay under ignored `.local/`; retained public reports contain no private paths or credentials.

Rebuild the assets and compare `comparison.json` with the retained build report. Browser timing naturally varies; inspect all raw repetitions and compare request/body counts and selected-geometry hashes. Source hashes and the dirty flag identify modified tooling. The benchmark is deliberately outside default CI/e2e discovery and runs only on explicit invocation.

Validation: 730 unit tests passed (101 Linux-only skips), six real PostGIS shape tests passed, Ruff lint/format and mypy passed, and the explicit browser run completed 48 verified loads. Unit regressions cover outside-area route shapes, overlapping route membership, release-independent objects, ordering/third-area stability, missing linkage and retained-source drift. Normal application browser/Compose flows were not changed; their PR CI remains separate. Progress is maintained in the [delivery plan](../delivery-plan.md).

# MAP-02: compressed loading and isolated heap measurements

This follows the [shape/route comparison](map-02-chunk-loading.md) with gzip delivery, browser download throttling and a separate JavaScript-heap experiment. Route grouping remains a serving candidate; the application, cloud resources, animation API and live capture are unchanged.

## Method and reproducibility

Both layouts use the same retained [comparison inputs](../../tests/fixtures/map02-expansion/chunk-comparison-report.json), complete tram routes and exact area selection. The shared experiment loader verifies decoded body length and SHA-256, checks duplicate geometry and filters to required shape IDs. Content hashes remain based on canonical decoded bytes: gzip is a transport encoding, not a different object identity.

The loopback HTTP/1.1 server precompresses each asset using gzip level 6, sends `Content-Encoding: gzip`, `Vary: Accept-Encoding` and immutable cache headers, and records actual compressed response-body bytes. Compression work happens before timing; the browser still decompresses, verifies and parses every object it reads, including cache hits. Body counts exclude headers/TLS. The no-compression report remains separate historical evidence.

Transport profiles are gzip with no throttle, and gzip with Chromium CDP configured for aggregate download throughput 125,000 bytes/second (1 Mbps) and minimum request-to-response-header latency 50 ms. These are controlled browser settings, not observed IAP conditions or a production network model. Geometry concurrency remains six; area/animation API request limits are unchanged. Each layout runs both area orders three times, alternating layout order between repetitions. Each pair starts in a fresh context; its second area reuses the real browser HTTP cache.

Memory is measured in separate unthrottled contexts so heap sampling and forced collection do not contaminate the transport timing table. Before each load, the previous selected geometry is released and garbage collection requested. `Runtime.getHeapUsage` samples V8 used size at intervals of at least 20 ms during loading. After loading, only the selected area geometry remains referenced; another collection measures retained heap, then the reference is released and collection repeated. Reports retain all samples plus used, allocated, embedder and backing-storage readings. Sampled maxima can miss brief allocations; retained deltas include harness/JIT effects. They are not renderer RSS, GPU/MapLibre memory or exact peak-memory acceptance.

## Recorded results

The [transport report](../../tests/fixtures/map02-expansion/chunk-transport-report.json) contains 48 loads; the [heap report](../../tests/fixtures/map02-expansion/chunk-memory-report.json) contains 24 separate loads. Both record clean source commit `5fb2f505aa98f24b5663dbab3f43369aed101c11`, Node 24.19.0, zlib `1.3.2.1-motley-3246f1b` and Chromium 153.0.8010.12. Gzip sizes can change with compressor version. The geometry digests match the original uncompressed experiment in every case.

Requests include the area manifest. Times are medians of three runs, in milliseconds; gzip bytes are exact compressed network response bodies.

| Area / cache | Layout | Requests | Gzip bytes | Decoded network bytes | Local ms | 1 Mbps / 50 ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Southbank cold | Shape | 209 | 1,033,089 | 2,617,143 | 130.8 | 10,032.8 |
| Southbank cold | Route | 13 | 781,979 | 3,212,510 | 48.2 | 6,528.4 |
| CBD cold | Shape | 367 | 1,674,194 | 4,227,364 | 225.8 | 16,540.9 |
| CBD cold | Route | 23 | 1,220,989 | 4,991,612 | 68.5 | 10,116.9 |
| CBD after Southbank | Shape | 164 | 671,742 | 1,701,212 | 188.3 | 6,952.9 |
| CBD after Southbank | Route | 11 | 440,986 | 1,786,120 | 65.2 | 3,752.5 |
| Southbank after CBD | Shape | 6 | 30,637 | 90,991 | 92.2 | 445.7 |
| Southbank after CBD | Route | 1 | 1,976 | 7,018 | 42.2 | 137.4 |

Memory figures below use cold loads and MiB (1,048,576 bytes). Each is the median of three runs. The sampled maximum is **absolute V8 used heap**; retained delta subtracts each run's baseline after garbage collection. They are different measures and must not be added. Warm-load readings are in the raw report.

| Area | Layout | Sampled maximum used heap, MiB | Post-GC retained delta, MiB |
| --- | --- | ---: | ---: |
| Southbank | Shape | 6.33 | 2.81 |
| Southbank | Route | 6.60 | 2.81 |
| CBD | Shape | 10.25 | 4.50 |
| CBD | Route | 10.11 | 4.50 |

Fast loads yielded only a few samples (minimum three including the final sample across this experiment). The CBD route figure being slightly below shape does not establish a lower peak; brief route decode allocations may fall between samples.

## Interpretation and remaining gate

Although route objects contain more decoded geometry, grouping improves gzip compression enough that cold **network bodies are smaller**: approximately 24% less for Southbank and 27% less for CBD than individually compressed shape objects. At the configured constrained profile, cold loading is about 35% and 39% faster respectively. This is stronger evidence for route grouping than the earlier uncompressed comparison, while preserving the decoded-byte and invalidation trade-offs.

After filtering and garbage collection, retained geometry costs are similar because both loaders keep the same shapes. That does not remove transient overfetch, array-buffer or parsing costs; those remain visible in raw heap/backing-storage readings, and the sampling cannot establish exact peaks. No in-memory decoded-object cache is assumed, so warm HTTP cache hits are still verified and parsed.

The experiment does not load a map or tram models. Actual HTTPS/HTTP2 serving through IAP, rendering/FPS, constrained devices, failure/fallback integration and release churn remain before production acceptance. A shape change replaces all route objects containing it. No production chunk policy is silently selected by these measurements.

## Reproduce

Generate `.local/chunk-comparison` using the pinned-source builder in the previous evidence. Install the locked web dependencies and Playwright Chromium, then run from the repository root:

```bash
node --test scripts/tram_chunk_experiments.test.mjs
node scripts/benchmark_tram_transport.mjs --assets .local/chunk-comparison --output .local/chunk-transport.json --mode transport
node scripts/benchmark_tram_transport.mjs --assets .local/chunk-comparison --output .local/chunk-memory.json --mode memory
```

Run timing and memory commands sequentially. `--repeats` defaults to three. Worktrees can use `--web-root <checkout>/apps/web`; the lockfile must match. Reports include exact source commit, dirty flag, source hashes, Node/zlib/Chromium versions and input-report hash. Timings and memory vary; compare repetitions, selected-geometry hashes and byte/request counts. Run only with trusted generated comparison assets. No provider credentials or cloud access are used.

Fast Node helper tests run in CI; long browser experiments remain explicit opt-in commands. Regression cases cover gzip/identity delivery, decoding and cache headers, body accounting, hash failures, missing objects/required shapes, conflicting route duplicates and invalid reference paths. The original uncompressed benchmark uses the same loader so these checks protect both experiments.

Validation: 730 Python unit tests passed (101 Linux-only skips); seven Node helper tests passed and are now included in CI. The original uncompressed harness completed 16 regression loads with identical request counts, byte counts and geometry to its retained baseline. The 48 transport and 24 memory loads also matched that geometry. Ruff lint/format, mypy and pinned actionlint passed. Application runtime and PostGIS behavior are unchanged in this PR.

Progress remains in the [delivery plan](../delivery-plan.md).

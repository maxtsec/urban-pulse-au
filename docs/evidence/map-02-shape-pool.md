# MAP-02: order-independent shape-pool build

This offline build addresses the [CBD serving-layout finding](map-02-cbd-expansion.md#serving-gate-order-independent-shape-pool). Geographic files remain source fixtures, while generated pool objects have no owning area. It establishes deterministic object selection and integrity; the browser loader and serving-performance acceptance remain separate.

## Object and area identity

`full-shape-content-v1` uses one complete shape per object. Canonical JSON has sorted keys, compact separators, finite numbers and a trailing LF. Each object includes its schema/policy version and the complete feature (shape/segment/route IDs, original ordered WGS84 coordinates and cumulative EPSG:32755 metre distances from the full shape origin). It is addressed as `objects/<sha256>.json`. Source order, outside-area spans and coincident vertices remain unchanged. Two shape IDs are not merged merely because their geometry looks alike.

Each area manifest contains its area identity, boundary hash, source attribution, policy and only its own shape-ID references. Its `source_revision` is the tram member hash; the full statewide archive hash and publication date remain in manifest provenance. Objects contain neither release hash nor publication date, so a bus-only release or an unchanged tram shape in a later tram release reuses the same object address. A changed feature changes only its own object; manifests record the new provenance and references. The offline CLI still requires the retained source pins; refreshing actual source inputs remains a reviewed operation. References carry the object path, hash and exact byte count. The manifest itself is addressed as `areas/<sha256>.json`. A hashed report provides discovery and measurements; it is build evidence, not the browser's global download list. Adding an area changes discovery but cannot rename existing objects or unchanged area manifests. Sorting area/reference keys removes registration-order dependence.

The builder validates the retained source/member identity, asset hashes/lengths, boundary hash/name and exact asset ID lists before building. Duplicate identities, missing references and input paths outside the repository fail. Publishing uses complete temporary files plus create-only hard links; repeat builds verify existing bytes and do not overwrite corruption. A filesystem without hard-link support fails rather than replacing this with partial direct writes. This is an offline build, not a crash-durable collector store or a deployed object publication protocol.

## Measured transfer trade-offs

[Retained report](../../tests/fixtures/map02-expansion/shape-pool-report.json), reproduced from the [pinned two-area inputs](map-02-cbd-expansion.md).

| Requested area and cache state | Shape objects fetched | Manifest bytes | Total JSON bytes | Requests |
| --- | --- | --- | --- | --- |
| Southbank, cold | 208 | 41,758 | 2,617,143 | 209 |
| CBD, cold | 366 | 72,667 | 4,227,364 | 367 |
| CBD after a complete Southbank load | 163 | 72,667 | 1,701,212 | 164 |
| Southbank after a complete CBD load | 5 | 41,758 | 90,991 | 6 |

Warm rows assume all previous shape objects are verified and cached, but the target area's manifest is not cached. Totals exclude HTTP headers, compression, cache revalidation, transport latency and browser memory. The complete shared pool has 371 objects and 4,203,930 object bytes, plus two area manifests and the report. These are serialized build measurements, not network benchmarks.

CBD requires exactly its 366 shapes, regardless of whether Southbank was built or visited first. It no longer fetches five unrelated shapes. Nevertheless its cold JSON total is larger than the 4,121,433-byte standalone collection because per-object envelopes and manifest references cost bytes; 367 cold requests may also be expensive. Per-shape granularity is the simplest exact-selection baseline, not a claim of optimal serving performance. Measure bounded request concurrency, latency, parsing and memory before browser enablement. Any later route/bucket grouping needs its own measured byte/request trade-off and must preserve order independence; do not silently repack existing immutable policy-version URLs.

## Reproduce

No database, provider API, credentials or source ZIP is needed; the retained input hashes are checked offline. From the repository root:

```bash
uv run python -m scripts.build_tram_shape_pool --output .local/map-02-shape-pool
uv run pytest -q tests/unit/test_tram_shape_pool.py
```

The CLI returns a relative hashed report path. Compare that report's bytes with the retained report above; follow each manifest/object reference and verify its hash and byte count. Generated pool files stay outside Git until serving packaging has been reviewed.

Tests cover reversed area and shape order, CBD-only versus combined builds, a synthetic third-area addition, bus-only and tram-member release changes reusing all 371 objects, one-feature invalidation, unchanged geometry/provenance, exact required objects and cache reuse, duplicate/missing references, corrupted/missing source inputs, path escape, repeat-build immutability, failed atomic publication and the real CLI entry. The third-area test is a structural regression using synthetic geometry, not coverage acceptance for another suburb.

Validation: 725 unit tests passed, including 20 shape-pool cases (101 Linux-only skips). Ruff lint/format, the existing mypy scope of 76 files, 825 local file links and whitespace checks passed. The CLI reproduced the retained report and emitted 371 objects plus two area manifests; hashes and lengths were verified through those manifests. Database and browser suites were not rerun locally for this offline-only change; normal PR CI runs them.

Before serving: integrate bounded loading and hash verification, test missing/corrupt objects with labelled static fallback, measure real cold/warm requests and rendering, and keep area results independent of geometry availability. Live trip matching/tolerance, animation clocks/endpoints, model licensing and source-policy gates remain under the [animation contract](../architecture/tram-animation-input-contract.md). Progress stays in the [delivery plan](../delivery-plan.md).

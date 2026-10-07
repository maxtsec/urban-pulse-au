# MAP-02: CBD as the second geometry verification area

The architect selected Melbourne CBD as the second expansion check on 7 October 2026. Use **Melbourne (CBD), the City of Melbourne CLUE small area**, consistently with Southbank's boundary system. This verifies route geometry and payload growth; it does not add a selectable CBD city panel or approve CBD building, weather, planning or live-source coverage.

## Pinned inputs and selection

The [CBD boundary](../../tests/fixtures/melbourne-cbd.geojson) is extracted without coordinate changes from the same 4 October municipal response as Southbank. The retained response SHA-256 is `0413add24a676fde3469623c159f604cfcf2a6401dce9350128d4b7315459fe2`, already recorded in [SRC-01 evidence](src-01-source-feasibility.md). The extracted CBD artifact SHA-256 is `2cfcc8302af12973997f54ab5f25cc2dd9ad5a41c20f0d7f15516bca6b8c4b28` (canonical LF bytes). Attribution: City of Melbourne, [CLUE small areas](https://data.melbourne.vic.gov.au/explore/dataset/small-areas-for-census-of-land-use-and-employment-clue/), CC BY 4.0; feature extracted and descriptive metadata added.

Use the same DTP GTFS Schedule release and source/member hashes as the [Southbank foundation](map-02-trip-foundation.md). Read-only PostGIS selects each complete source shape with positive-length overlap with each area's polygon, including a shared boundary segment, without a buffer. Point-only contact is excluded. Source vertices, direction and complete outside-area spans stay intact; metre distances start at the source shape origin. Area boundaries select routes independently and never truncate route continuity.

The [area index](../../tests/fixtures/map02-expansion/index.json) references the existing [Southbank asset](../../tests/fixtures/map02/southbank-tram-shapes.geojson) plus [CBD's additional shapes](../../tests/fixtures/map02-expansion/cbd-additional-shapes.geojson). Each `(source release, shape_id)` occurs in exactly one asset. Per-area shape lists reference the shared identity; a route touching both areas is not copied. The builder rejects different content for a shared identity and refuses to refresh Southbank silently when its retained bytes differ. Source IDs use a portable order independent of database collation.

## Measured geometry growth

These are uncompressed canonical JSON bytes and vertex counts, not browser memory or rendered frame-rate measurements.

| Scope | Complete shapes | Vertices | Geometry bytes |
| --- | --- | --- | --- |
| Southbank alone | 208 | 54,589 | 2,556,499 |
| CBD alone | 366 | 87,898 | 4,121,433 |
| Two separately duplicated area assets | 574 entries | Includes shared vertices twice | 6,677,932 |
| Shared Southbank asset plus CBD additions | 371 unique shapes | Each shape retained once | 4,170,253 |

There are **203 shared shapes** and **163 additional CBD shapes**. Expanding the retained geometry adds **1,613,754 bytes**, about 63% over Southbank alone. Sharing saves 2,507,679 bytes compared with separate complete copies. The index and boundary files are additional metadata, excluded from the geometry column. Static shapes belong in immutable shared assets, not each bounded animation response or every 2D snapshot.

## Serving gate: order-independent shape pool

The current primary-plus-additions layout is **offline verification storage only**, not the serving layout. A CBD-only cold load through this index would require both assets: 4,170,253 bytes rather than CBD's standalone 4,121,433 bytes. The extra 48,820 bytes include five Southbank-only shapes and an additional collection wrapper. The shared-storage saving above is not a CBD download saving. With more areas, assigning shape ownership to the first area can scatter later areas across several earlier files; request count and cold-load bytes would depend on area-addition history.

Before serving these shapes, replace geographic ownership with a shared pool whose chunk identities and membership do not depend on area registration order, for example content-addressed shape or route chunks. Each area's immutable manifest lists only its own shape IDs and resolves them to pool objects, with release/provenance and content hashes retained. Measure the trade-off between per-shape request count and any extra geometry in coarser chunks; do not reuse this offline index as the browser asset contract.

Serving acceptance must compare Southbank-first, CBD-first and a later third-area addition: an unchanged area's manifest, required object set and cold-load bytes must remain identical under the same source release and chunk policy. Also verify per-area completeness, shared-object cache reuse, hash/missing-object failure and bounded loading. Record both retained storage and per-area cold/warm transfer sizes separately. Shared geometry must not expand area membership or animation eligibility.

## Reproduce and validate

With local PostGIS and the retained pinned statewide ZIP:

```bash
uv run python -m scripts.build_tram_area_fixture --archive /path/to/retained/gtfs.zip --output /path/to/new/output
uv run pytest -q tests/unit/test_tram_area_fixture.py tests/unit/test_tram_fixture.py
uv run pytest -q -m integration tests/integration/test_tram_area_expansion.py tests/integration/test_tram_shapes.py
```

The builder reads source files and runs read-only spatial queries; it does not call live feeds or create database tables. Match the pinned PostGIS/GEOS/PROJ version recorded in the index when reproducing exact distance bytes. Compare both generated files byte-for-byte with the retained artifacts. The shared Southbank file must already match its pinned source build. Boundary and asset hashes, uniqueness, shared-content conflicts, per-area linkage, counts and byte totals have automated checks. Real PostGIS tests reselect both exact scope lists from the shared assets and verify unchanged full geometry and distance sequences.

Validation: 705 unit tests passed (101 Linux-only skips), 51 real PostGIS/persistence tests passed, and all five foundation/expansion artifacts reproduced byte-for-byte. Ruff lint/format, mypy (76 source files), 814 local file links and whitespace checks passed. Browser rendering is outside this offline verification slice; the normal browser/Compose suite runs in PR CI.

## Remaining expansion work

- Keep network-wide tram collection shared: adding this area does not require a second copy of the same realtime feed. Normalized retained history and upload volume can still grow; choose the retained geography before the raw retention window expires if later CBD history is needed.
- Keep geometry availability separate from vehicle membership, city-event scope and area results. A shape crossing both areas does not place all its vehicles in both areas. Before adding a CBD panel, pin its scope/timeline and test independent assessment and cache identity.
- Measure first-load bytes, parsing/memory, viewport requests and frame rate before serving the larger shape set. Reuse immutable assets across area switches; avoid increasing the bounded animation envelope to carry geometry. Missing assets keep the labelled static fallback.
- Verify CBD building and planning coverage and weather applicability separately. The current synthetic Southbank data and accepted rules do not prove another area's coverage. Missing inputs remain unknown.

Progress is maintained in the [delivery plan](../delivery-plan.md).

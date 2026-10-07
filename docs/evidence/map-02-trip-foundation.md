# MAP-02 trip and shape foundation

This slice implements the transport/GTFS prerequisites of the [accepted animation contract](../architecture/tram-animation-input-contract.md). It adds no animation endpoint, live adapter, clock migration or 3D model. Existing city fixtures, persisted identities and the displayed map remain unchanged; the new fixture is independently retained for the next animation slice.

## Compatible transport metadata

`VehiclePosition.trip` is optional and nullable. When present, `trip_id`, `service_date` (GTFS `start_date`, `YYYYMMDD`), `start_time` (GTFS service time, allowing hours beyond 24) and `direction_id` (integer 0/1) can each be unknown. Dates must be real calendar dates. Missing identity is not sufficient for animation and must not be filled from route alone. Direction copied from a static schedule is not a live producer observation.

Absent `trip` remains absent in Python/JSON serialization, including nested envelopes. Explicit null remains explicit. Tests pin the pre-change serialized-payload and receipt hashes for the retained standalone event and all eight valid city-fixture frames. Unknown optional fields remain forwardable. New trip content participates in event fingerprinting. No source event receives a fabricated `shape_id`; static linkage remains a separate derived view.

## Retained assets and provenance

[Manifest](../../tests/fixtures/map02/manifest.json), [clipped shapes](../../tests/fixtures/map02/southbank-tram-shapes.geojson), [synthetic observations](../../tests/fixtures/map02/trip-observations.json).

| Item | Result |
| --- | --- |
| Official release | DTP GTFS Schedule; retained archive Last-Modified 2026-10-04T01:31:37Z |
| Statewide ZIP SHA-256 | `7eb6562c7b19f5685740f3da9f95440bd964681b76c9dc5854f4cb4d08ae393d` |
| Tram member | `3/google_transit.zip`; SHA-256 `df140ec0fd415d9ce3bd45ff3a47dbb8a65668168fe20a5fd442dc5fa0a62536` |
| Shapes | 535 source shapes; 208 retained, 327 excluded; 317 contiguous clipped components |
| Geometry size | 359,173 bytes; exact geometry hash recorded in the manifest |
| Synthetic observations | Six events, two active scheduled trip identities, both directions of route 1; five-second authored receipt delay |
| Source-use | Department of Transport and Planning, Victoria; [GTFS Schedule](https://opendata.transport.vic.gov.au/dataset/gtfs-schedule), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |

The builder verifies both archive hashes before reading source rows. It reads CSV/GeoJSON as UTF-8, rejects duplicate shape sequences, invalid coordinates, ambiguous trip IDs and dangling route/shape references, and orders source vertices numerically. Selected trips have service active on 7 October 2026 and are not frequency-based. Their start time comes from the first static stop sequence. The fixture's vehicle, movement and observation/receipt instants are authored; they do not claim those scheduled services actually occupied those points at those times.

Each original edge is transformed from WGS84 to EPSG:32755 and intersected with the retained Southbank polygon, with no buffer. Positive-length pieces retain source traversal order. Cumulative distances start at the original full shape origin, including excluded spans; they do not reset at the boundary. Reverse-direction shapes remain reversed. Holes and excluded spans produce different `segment_id` components, never a straight-line bridge. Output returns to WGS84 at 12 decimal places without simplification. GTFS `shape_dist_traveled` is not assumed to use metres.

The manifest retains included/excluded shape IDs, component counts, route IDs, boundary hash, coordinate/distance conventions, build-library versions, source licence/attribution and artifact byte hashes. Full source archives remain outside Git. The component IDs are stable within this pinned release and extraction policy, not a promise across future GTFS releases.

**Live matching is still open.** The manifest deliberately leaves matching algorithm/tolerance null. Geometry extraction and synthetic points selected from those shapes do not measure GPS snapping quality, ambiguous branches, real trip-instance continuity or a live freshness/correction rule. Those decisions and tests precede interpolating live positions. A third-party tram model and its licence remain separate.

## Rebuild and validate

Use the retained official statewide ZIP identified above; a different current download will fail the hash check. A source refresh requires a reviewed new pin and regenerated artifacts. From the repository root with the local PostGIS service available:

```bash
uv run python -m scripts.build_tram_fixture --archive /path/to/retained/gtfs.zip --output /path/to/new/output
uv run pytest -q tests/unit/test_events.py tests/unit/test_tram_fixture.py
uv run pytest -q -m integration tests/integration/test_tram_shapes.py tests/integration/test_city_inputs.py tests/integration/test_event_store.py
```

The builder uses a read-only database transaction and creates no database tables. Compare every output byte with `tests/fixtures/map02/` using the same pinned PostGIS/GEOS/PROJ versions recorded by the manifest. Exact artifact reproduction passed against the retained archive; all three files matched byte-for-byte. Other geometry-library versions may produce different intersection precision and must not silently refresh reviewed hashes.

Validation includes pre-change wire/receipt golden tests, missing/null/partial trip metadata, malformed dates/times/directions, trip-change fingerprints, artifact hashes, shape order and direct fixture linkage. Real PostGIS tests cover traversal direction, retained distance offsets, polygon holes, point-only contact and boundary containment; a 2 cm round-trip numeric allowance in the containment test is not a matching tolerance or a domain membership buffer. The full local unit run passed 700 tests (101 Linux-only skips); 47 real PostGIS/persistence tests also passed. Ruff lint/format and mypy (76 source files) passed. Browser, Compose and the broader database suite are covered by PR CI; no browser behavior changed in this slice.
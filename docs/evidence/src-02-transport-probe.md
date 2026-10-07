# SRC-02: Bounded tram access and GTFS linkage probe

Measured 7 October 2026, 03:44:15–03:46:36 UTC (14:44–14:46 Melbourne daylight time). This is a short network-wide sample, not a Southbank coverage or production freshness guarantee. Progress remains in the [delivery plan](../delivery-plan.md).

## Access and sample bounds

Two preliminary positions requests used the same locally configured credential with different headers: `Ocp-Apim-Subscription-Key` returned **401**, then `KeyID` returned **200**. The key was sent only to the fixed official HTTPS endpoint, never in a URL. No error body or credential is published. This establishes the working header for this subscription on this date, not the provider's account-wide quota.

The subsequent finite run made **11 requests**, all HTTP 200: positions at offsets 0/30/60/90/120 seconds; updates at 10/70/130; alerts at 20/80/140. One request at a time, at least ten seconds between starts, no retries or redirect following. The tool stops on any HTTP failure, including 429. The 20–27 versus 24 calls/minute documentation discrepancy remains unresolved; no load test was attempted.

Official references: [collection and licence](https://opendata.transport.vic.gov.au/dataset/gtfs-realtime), [positions OpenAPI](https://opendata.transport.vic.gov.au/dataset/2d9a7228-5b81-40d3-8075-ae7a3da42198/resource/a42c2344-38da-4c52-805b-36004dea3cac/download/gtfsr_yarra_trams_vehicle_positions.openapi.json), [GTFS Schedule](https://opendata.transport.vic.gov.au/dataset/gtfs-schedule), [GTFS-Realtime reference](https://gtfs.org/documentation/realtime/reference/). Department of Transport and Planning, Victoria; CC BY 4.0. Tables are UrbanPulse-derived measurements, not provider forecasts or official operating limits.

## Payloads and changes

| Feed | Samples | Entities per sample | Raw bytes | Gzip bytes | Identical raw transitions | Identical entity transitions |
| --- | --- | --- | --- | --- | --- | --- |
| vehicle-positions | 5 | 114–117 | 13,868–14,229 | 3,185–3,243 | 0/4 | 0/4 |
| trip-updates | 3 | 425–430 | 85,444–87,229 | 19,696–20,023 | 0/2 | 0/2 |
| service-alerts | 3 | 1–3 | 955–2,130 | 388–683 | 0/2 | 1/2 |

Gzip is an offline size experiment (level 6, mtime 0), not an accepted storage encoding. Environment: CPython 3.12.15, zlib 1.3.2, `gtfs-realtime-bindings` 2.2.0. Wire decoding uses the official generated bindings. Raw bytes and their SHA-256 remain separate from the diagnostic entity fingerprint, which sorts deterministic entity encodings and excludes the feed header. It is not a domain revision fingerprint.

The first two alerts payloads have different raw hashes but identical entities: the feed header changed. Consequently raw-byte inequality alone is not evidence of a changed disruption. The last sample contains three alert entities. These samples do not establish complete alert coverage or that each alert applies to Southbank.

## Trip and shape linkage

The pinned mode-3 archive contains **63,073 trips, 24 routes and 535 shapes with at least two rows**. No duplicate trip IDs or absent shape references were found. It is the exact `3/google_transit.zip` member of the previously downloaded official statewide archive:

| Artifact | SHA-256 |
| --- | --- |
| Statewide `gtfs.zip` | `7eb6562c7b19f5685740f3da9f95440bd964681b76c9dc5854f4cb4d08ae393d` |
| Mode-3 `tram.zip` | `df140ec0fd415d9ce3bd45ff3a47dbb8a65668168fe20a5fd442dc5fa0a62536` |

The source download metadata records `Last-Modified: Sun, 04 Oct 2026 01:31:37 GMT`. The mode-3 calendar rows span 1 October–31 December; this range does not establish complete timetable coverage throughout that period. Each observed service date is checked against its own calendar and exception rows.

All **577 position records** and **1,281 trip-update records** across the samples linked by exact trip ID to one static trip, agreed with its route, referenced an existing shape and had active service on the supplied `start_date`. Counts include repeated records across captures, not distinct vehicles/trips. No suffix or fuzzy matching was used. Every sampled trip supplied `trip_id`, `route_id`, `start_date` and `start_time`, but none supplied `direction_id`; timetable direction must retain its static provenance if used later.

`linked` here is a referential/calendar check. It does not validate start-time consistency with stop times, geometry quality, distance along the shape, Southbank membership or unambiguous animation continuity. Frequency-based and non-scheduled trips are deliberately reported as unverified by this tool. Those cases and physical shape matching belong to MAP-02 implementation.

## Position age and movement

| Position offset (s) | Vehicles | Median age (s) | Age >120s | Age >300s | Changed coordinates / shared vehicles |
| --- | --- | --- | --- | --- | --- |
| 0 | 115 | 99.2 | 21 | 9 | 0/0 |
| 30 | 114 | 108.1 | 29 | 9 | 43/112 |
| 60 | 116 | 90.2 | 14 | 8 | 102/112 |
| 90 | 115 | 118.4 | 44 | 9 | 34/112 |
| 120 | 117 | 106.1 | 22 | 9 | 69/113 |

Age uses each vehicle's original `timestamp` against response receipt time; medians use the lower middle observation. The maximum age grew from 4,666 to 4,786 seconds. All sampled positions included a vehicle ID, observation timestamp and finite in-range coordinates. The 120/300-second columns use existing fixture thresholds **for comparison only**, not an approved live TTL. A 30-second display delay cannot by itself make these old observations current.

At the 60-second sample one shared vehicle changed coordinates without changing its observation timestamp. The production adapter must retain the existing conflict/correction guard until a source correction rule is accepted; this measurement does not authorize ordering changed content by fetch time. Missing vehicles between full snapshots also need explicit disappearance semantics before live projection.

All sampled trip updates omitted their per-trip update timestamp and vehicle ID. Their feed-header time is distinct from an observation timestamp; the tool leaves observation age unknown. Do not manufacture a vehicle identity from the entity ID or replace missing observation time with capture time.

## Validation and next decisions

Local validation: Ruff lint/format and mypy passed; 630 non-integration tests passed, including 30 new probe tests. All 11 retained sample summaries were reproduced offline against their original receipt timestamps and checked payload hashes. Existing database integration, browser and Compose suites are left to PR CI because application runtime is unchanged.

Synthetic tests cover exact/ambiguous linkage, service-date exceptions, frequency trips, missing timestamps, duplicate vehicle IDs, raw versus entity changes, malformed protobuf, bounded request scheduling, HTTP/network failures, redirects, size limits, offline execution and the probe lock. [Runbook](../runbooks/transport-source-probe.md) describes reproduction and private retained evidence. No source payloads, API keys, cloud resources or application API changes are included in this PR.

Before continuous collection: confirm subscription quota scope; approve per-source retention and attribution; measure longer and across service-day boundaries before accepting live freshness/correction rules. Before animation: validate shapes and trip instances, then implement the accepted nullable trip contract and synthetic fixtures. Open-Meteo, VicEmergency and planning SRC-02 checks remain separate.

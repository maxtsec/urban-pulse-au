# SRC-01: Source feasibility and pilot comparison

Reviewed: 4 October 2026 (Australia/Sydney). This record combines official documentation with bounded public-data queries. [Delivery status](../delivery-plan.md) and [architect decisions](../adr/0002-southbank-tram-pilot.md) are maintained separately.

## Geography measured

The comparison uses City of Melbourne [CLUE small-area boundaries](https://data.melbourne.vic.gov.au/explore/dataset/small-areas-for-census-of-land-use-and-employment-clue/), [Development Activity Monitor (DAM)](https://data.melbourne.vic.gov.au/explore/dataset/development-activity-monitor/), and DTP [Public Transport Stops](https://opendata.transport.vic.gov.au/dataset/public-transport-lines-and-stops/resource/dc5a9bdc-b79e-4806-8288-2a983db30930). Both municipal datasets identify CC BY 4.0 in their API metadata; DTP also publishes the stops under CC BY 4.0. Attribution: City of Melbourne and Department of Transport and Planning, Victoria; counts below are our spatial analysis.

| CLUE area       | Tram stop records | Metro bus stop records | Metro train stop records | DAM records | Applied | Approved | Under construction | Completed |
| --------------- | ----------------- | ---------------------- | ------------------------ | ----------- | ------- | -------- | ------------------ | --------- |
| Southbank       | 24                | 9                      | 0                        | 128         | 7       | 29       | 5                  | 87        |
| Melbourne (CBD) | 84                | 41                     | 131                      | 335         | 7       | 49       | 11                 | 268       |
| Carlton         | 21                | 38                     | 2                        | 142         | 5       | 16       | 8                  | 113       |

These are stop records, including platform-level records, rather than counts of stations, routes or operating services. Zero train points inside Southbank does not mean residents cannot reach a nearby station. No catchment buffer was applied. A static stop is not evidence of a currently operating vehicle or a successful realtime/static join.

All 605 pilot development keys were unique across the three areas. Every pilot development point fell within its named CLUE polygon. A separate dataset-wide query found no null geopoints among the 1,450 DAM records. These checks establish snapshot consistency, not permanent identity or complete development coverage.

Our inference: Southbank offers a compact tram-and-development demonstration; CBD offers more transport variety and more records; Carlton is another feasible static-data candidate. The same Victorian warning products are candidates for all three, but no live warning footprint or authenticated transport payload was measured. Three-domain live overlap remains conditional on weather access and spatial interpretation.

## Dataset time and meaning

| Dataset                          | Published cadence | Observed data timestamp                                             | Consequence                                                                                            |
| -------------------------------- | ----------------- | ------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| DAM                              | Monthly           | Data processed 24 September 2026                                    | Display snapshot time separately from completion year; do not infer a change time for each development |
| CLUE small areas                 | Annually          | Data processed 13 November 2022; metadata modified 3 September 2026 | Metadata freshness does not prove new geometry; pin the downloaded boundary revision                   |
| Public Transport Lines and Stops | Weekly            | Collection modified 28 September 2026                               | Use for the feasibility comparison; obtain compatible GTFS Schedule for realtime joins                 |

Municipal timestamps and cadence came from the [DAM metadata API](https://data.melbourne.vic.gov.au/api/explore/v2.1/catalog/datasets/development-activity-monitor) and [CLUE metadata API](https://data.melbourne.vic.gov.au/api/explore/v2.1/catalog/datasets/small-areas-for-census-of-land-use-and-employment-clue); transport cadence came from the [DTP collection](https://opendata.transport.vic.gov.au/dataset/public-transport-lines-and-stops).

CLUE explicitly differs from gazetted suburb and postcode boundaries. DAM describes major developments, with inclusion thresholds in its [field guide](https://data.melbourne.vic.gov.au/api/datasets/1.0/development-activity-monitor/attachments/dam_info_dam_may_2016_meta_data_info_pdf/). It is useful area-profile context, not a complete works/road-incidents feed. Preserve provider statuses without converting development volume into a health score. The API exposes `development_key`, `clue_small_area`, `status`, `year_completed` and point coordinates; no per-record update timestamp was found in its schema.

## Transport: usable direction, conflicting access documentation

The [GTFS-Realtime collection](https://opendata.transport.vic.gov.au/dataset/gtfs-realtime) lists positions, trip updates and alerts for Metro and Yarra Trams; the bus listing has positions and trip updates. It publishes CC BY 4.0. Its Tram description and the downloadable API definitions disagree:

| Detail                | Collection page                  | Tram OpenAPI definitions                         |
| --------------------- | -------------------------------- | ------------------------------------------------ |
| Authentication header | `KeyID`                          | `Ocp-Apim-Subscription-Key`                      |
| Request limit         | 24 calls per 60 seconds for Tram | 20-27 calls per minute depending on payload size |
| Timing                | Refresh every 60 seconds         | Cache time 30 seconds                            |

The three definitions share `https://api.opendata.transport.vic.gov.au/opendata/public-transport/gtfs/realtime/v1/tram` with paths `/vehicle-positions`, `/trip-updates` and `/service-alerts`. See the official [positions definition](https://opendata.transport.vic.gov.au/dataset/2d9a7228-5b81-40d3-8075-ae7a3da42198/resource/a42c2344-38da-4c52-805b-36004dea3cac/download/gtfsr_yarra_trams_vehicle_positions.openapi.json), [trip-updates definition](https://opendata.transport.vic.gov.au/dataset/2d9a7228-5b81-40d3-8075-ae7a3da42198/resource/1ae333b0-b822-4137-9060-7b0f9843bf4e/download/gtfsr_yarra_trams_trip_updates.openapi.json) and [alerts definition](https://opendata.transport.vic.gov.au/dataset/2d9a7228-5b81-40d3-8075-ae7a3da42198/resource/c1affc17-233b-4124-9e43-457267595d65/download/gtfsr_yarra_trams_service_alerts.openapi.json). Cache lifetime and publication cadence measure different things; neither establishes observed vehicle freshness.

Resolve the active header and quota scope through the subscription portal/provider and a bounded authenticated probe before enabling polling. Keep the key server-side in a header, with a single request budget across workers and retries. No credentials were requested or tested in this research.

Proposed initial budget for review: poll vehicle positions every 30 seconds, and trip updates and service alerts every 60 seconds. This schedules four requests per minute, with retries sharing a conservative ceiling of six total requests per minute. Stagger requests and share the budget across workers. Browser sessions read our projection rather than multiplying upstream calls. Confirm the active quota and its scope before enabling this schedule.

The documented 30-second cache makes the faster position poll worth evaluating, but the collection still describes a 60-second Tram refresh. Polling twice per minute may therefore return the same observation. Measure source timestamps and consecutive position changes before setting UI freshness or animation behavior; repeated payloads must not refresh a vehicle's observation time. This is an application proposal, not a provider guarantee or an accepted operating policy.

[GTFS Schedule](https://opendata.transport.vic.gov.au/dataset/gtfs-schedule) is published weekly, covers a rolling 30-day period and warns that paths can be approximate. Before live acceptance, match trip/route/stop IDs to a pinned compatible schedule; measure timestamp age, missing IDs and coordinates, consecutive position changes and alert coverage. The [GTFS-Realtime reference](https://gtfs.org/documentation/realtime/reference/) makes vehicle timestamps and some identifiers optional. Preserve absence explicitly; a new fetch must not make an old position fresh. A realtime entity ID must not automatically become a permanent vehicle ID.

## Weather: exact products and the remaining access gap

The [BOM warning guide](https://www.bom.gov.au/catalogue/Bureau_of_Meteorology_warning_products_user_guide.pdf) identifies Victorian severe-weather products `IDV21037` and `IDV21038` (pages 38-39), allowing concurrent warnings. CAP XML is listed; warnings update at least every six hours, with cancellation in the same products. District AAC references provide coarse coverage. The guide places precise boundary-coordinate files in a registered service. Its CAP appendix describes `msgType=Cancel` for severe-weather sequences, while other hazards can end differently (pages 59-60).

Recommendation: investigate both severe-weather products as the first warning slice, retaining issue/revision/expiry and official links. Require permitted sample access to verify identifiers, references and geometry. If only district coverage is available, show district-level applicability explicitly; do not draw an invented Southbank warning polygon. Exact polygon intersection and any area-status effect need A-03/A-04 agreement. Heat, flood and observations remain separate product evaluations.

[BOM's data catalogue](https://www.bom.gov.au/catalogue/data-feeds.shtml) describes anonymous products as non-commercial and subject to product/default terms. The [copyright notice](https://www.bom.gov.au/copyright) limits default use to personal/internal use without onward supply unless permission is given. Therefore this review does **not establish permission** for public warning redistribution, retained public samples or a historical warning archive. Product-specific permission or a suitable data agreement is needed before those uses.

[Victoria RSS](https://www.bom.gov.au/rss/) offers a link-oriented alternative under personal/non-commercial terms, attribution and direct-link requirements. It does not establish precise warning geometry or broader archive rights. A link-only regional warning panel would be a separate product decision, not a silent replacement for the integrated weather slice. Use synthetic warning fixtures while this is resolved.

## Reproduce the comparison

Read-only requests need no provider credentials. Results will change as publishers update their data. Local research files are under ignored `.local/src01/`; raw payloads and credentials are not part of this PR.

1. Read the municipal metadata URLs above and DTP's [CKAN collection metadata](https://opendata.transport.vic.gov.au/api/3/action/package_show?id=public-transport-lines-and-stops). Resolve the resource named `Public Transport Stops`; resource UUIDs can change. The current download was 8,416,967 bytes and contained 32,032 point features. The download was bounded to 12 MB with a 30-second timeout.
2. Fetch `/api/explore/v2.1/catalog/datasets/small-areas-for-census-of-land-use-and-employment-clue/records?limit=20` on the municipal host. All 13 rows fit. Extract `geo_shape.geometry` for the three named `featurenam` values and verify valid polygons.
3. Query DAM `/records` with the parameters below, using offsets 0, 100, 200, 300, 400, 500 and 600. Stop at the response's `total_count`; verify 605 rows and unique development keys. Each response was bounded to 2 MB with a 30-second timeout.

```text
select=development_key,clue_small_area,geopoint,status
where=clue_small_area in ('Southbank','Melbourne (CBD)','Carlton')
order_by=development_key
limit=100
```

4. Use longitude/latitude ordering for both sources. This run used Python 3.12 and Shapely 2.1.2 in a temporary uv environment, without modifying project dependencies. Count stop points by `MODE` where the CLUE polygon `covers(point)`; verify unique `(MODE, STOP_ID)` pairs. No included stop lay exactly on a polygon boundary. Apply the same predicate to each development's named area. This research predicate is not yet the approved production edge/catchment policy.
5. Independently group DAM by `clue_small_area,status` with `count(*)` and compare the counts. Check missing coordinates with `where=geopoint is null` and `select=count(*)`. The observed null set was empty. Grouped counts and all pilot point checks agreed.

Checksums identify the local evidence bytes. The boundary file is the API response saved as UTF-8; the planning file is a JSON serialization of the combined seven pages. Re-fetching or changing JSON serialization may change hashes.

| Local evidence                | SHA-256                                                            |
| ----------------------------- | ------------------------------------------------------------------ |
| `stops.geojson`               | `2d8b452f088a54c7d9c390ab5ccf2f6d383afd82fc95c4427a3ffdf354c26daa` |
| `boundaries.json`             | `0413add24a676fde3469623c159f604cfcf2a6401dce9350128d4b7315459fe2` |
| `planning-pilot-records.json` | `58b0d93bc75b7f9514deca40f3bfbb63feb700d99ea40fd73df0f61eacfecbc2` |

The authenticated transport probe, BOM permission/sample validation and live cadence measurements are separate enablement gates in the [source register](../source-register.md). No collector, provider subscription or cloud resource was created by this comparison.

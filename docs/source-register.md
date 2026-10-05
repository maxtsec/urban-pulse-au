# Source register

Reviewed: 6 October 2026. This register owns source evidence and enablement requirements. Integration progress is in the [delivery plan](delivery-plan.md). Measurements and official references are in the [SRC-01 evidence](evidence/src-01-source-feasibility.md).

## Source scope and enablement gates

The architect selected **Southbank CLUE** and **Yarra Trams positions, trip updates and alerts**, with compatible static GTFS, in [ADR 0002](adr/0002-southbank-tram-pilot.md). Source selection does not itself enable live capture.

| Domain                    | Product                                                                                                                                                                          | Verified evidence                                                                                                                                                             | Before live enablement                                                                                                                                                       |
| ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Transport                 | [DTP GTFS-Realtime](https://opendata.transport.vic.gov.au/dataset/gtfs-realtime), Yarra Trams, plus [GTFS Schedule](https://opendata.transport.vic.gov.au/dataset/gtfs-schedule) | Three Tram feeds; CC BY 4.0; published authentication/quota discrepancy documented in SRC-01                                                                                  | Verify active header and quota scope, supply server-side credentials, test static/realtime IDs, position freshness and alert coverage; accept attribution and capture policy |
| Weather & Hazards | [Open-Meteo](https://open-meteo.com/en/docs), modelled readings | [Terms](https://open-meteo.com/en/terms) describe free non-commercial access and CC BY 4.0 data; [ADR 0005](adr/0005-weather-source-policy.md) selects informational use | Confirm application eligibility, attribution, chosen variables/model, effective times, cadence, quotas and retention; modelled data cannot supply warning coverage; forecasts need later scope approval |
| Weather & Hazards | VicEmergency candidates: severe weather, severe thunderstorm, riverine flood and flash flood warnings; verify each separately | [Official support](https://support.emergency.vic.gov.au/hc/en-gb/articles/235717508-How-do-I-access-the-VicEmergency-data-feed) directs prospective feed users to submit a request; the 5 October maintainer browser review of the EMV notice records State of Victoria copyright and CC BY 3.0 Australia; see evidence below | Confirm supported endpoint (candidate: `https://emergency.vic.gov.au/public/osom-geojson.json`), licence including third-party content, polling, retention, category/level mappings, geography and complete-snapshot/lifecycle semantics |
| Weather & Hazards | Later source: BOM products, including candidate severe-weather products IDV21037 and IDV21038 | [Warning guide](https://www.bom.gov.au/catalogue/Bureau_of_Meteorology_warning_products_user_guide.pdf) documents product lifecycle and geography | Obtain product-specific use/access terms; review product scope, severity and coverage before adding an adapter; preserve differences from modelled readings and VicEmergency warnings |
| Planning & Infrastructure | [City of Melbourne Development Activity Monitor](https://data.melbourne.vic.gov.au/explore/dataset/development-activity-monitor/)                                                | Public API, CC BY 4.0, monthly cadence; 128 Southbank records; all pilot points matched named polygons in the inspected snapshot                                              | Accept this planning slice and retention duration; define identity/change/deletion handling and attribution; verify capture/retrieval                                        |
| Spatial foundation        | [CLUE small areas](https://data.melbourne.vic.gov.au/explore/dataset/small-areas-for-census-of-land-use-and-employment-clue/)                                                    | Southbank selected; CC BY 4.0; boundary geometry and publication timestamps inspected                                                                                         | AREA-01 defines internal ID, version/hash, coordinate validation, boundary-edge and catchment rules                                                                          |
| Road incidents/works      | Additional official source to evaluate separately                                                                                                                                | GTFS and DAM do not establish comprehensive road incident or works coverage                                                                                                   | Verify access, spatial/temporal fields and ownership before adding a road layer                                                                                              |
| Map context (proposed) | [City of Melbourne 2023 Building Footprints](https://data.melbourne.vic.gov.au/explore/dataset/2023-building-footprints/) for 3D massing; GTFS Schedule shapes for tram tracks; [Vicmap Transport Road Line](https://discover.data.vic.gov.au/dataset/vicmap-transport-road-line) for simulated traffic paths; 3D model assets | Footprints: CC BY 4.0, stacked AHD heights, 1,189 polygons intersect Southbank (6 October 2026). GTFS Schedule and Vicmap Road Line: CC BY 4.0 | Direction accepted in [ADR 0011](adr/0011-southbank-building-massing.md); per-source verification and fixture manifests, attribution and the records in [map context sources](#map-context-sources) |

The candidate warning scope includes severe weather, severe thunderstorm, riverine flood and flash flood. Riverine flooding is relevant to the Southbank/Yarra pilot; inclusion as a candidate does not prove local applicability or complete feed coverage. Verify and enable each product independently. Heat and station observations require separate product evaluation. The provider category `Met` is not an accepted substitute for that evaluation. Fire, hazmat and road incidents are outside this slice. Preserve official severity and source links; an application status is not official emergency guidance.

## Access and use policy

[DTP and municipal CC BY 4.0 licensing](https://creativecommons.org/licenses/by/4.0/) permits sharing and adaptation subject to attribution, licence links and change notices. Proposed credits identify the Department of Transport and Planning, Victoria, or City of Melbourne, the specific dataset and modifications made by UrbanPulse. Preserve source notices in any published sample. The project must still choose retention duration, storage budget and access controls; those values are not implied by the licence.

BOM's [default terms](https://www.bom.gov.au/copyright) and [RSS terms](https://www.bom.gov.au/rss/) do not establish the required public application/archive rights for the candidate warning products. Obtain product-specific terms or permission before those uses. Use synthetic warning fixtures in the meantime; no BOM content was captured for public fixtures during SRC-01.

Transport collection metadata and Tram OpenAPI definitions disagree on authentication and quotas. Keep that discrepancy visible until resolved. A bounded successful probe must confirm the active contract; production polling must share its budget across workers and retries. Map tile access and attribution are a separate A-02 decision.

## Weather enablement evidence

A maintainer browser review of the original [EMV emergency-data notice](https://www.emv.vic.gov.au/responsibilities/victorias-warning-system/emergency-data) on 5 October 2026 confirmed State of Victoria copyright and **Creative Commons Attribution 3.0 Australia** licensing for the notice's feed data. The [attribution acceptance](#attribution-acceptance) below owns the display requirements and application receipt-time definition. This evidence comes from the browser review; automated retrieval still returned HTTP 403 on the same date.

The official support article still says the feed is not publicly available and invites requests. Confirm the supported endpoint and whether the notice covers embedded third-party content, including BOM material. The notice review does not resolve those questions, permitted retention or product completeness. A successful JSON fetch or a sample containing polygons does not establish exhaustive coverage or geometry meaning.

Ask for completeness by product, geography and relevant time; pagination/truncation, update, withdrawal/cancellation and outage semantics; and whether an empty successful snapshot establishes no active in-scope warnings. Unverified completeness keeps warning coverage unknown even when captures are recent. Geometry describes warning applicability, not necessarily observed impact.

### Candidate warning products

| Candidate | Verification before enabling it |
| --- | --- |
| Severe weather | Product/category identity, source level mapping, validity/update/cancellation, warning geography and complete-snapshot scope |
| Severe thunderstorm | Product/category identity and lifecycle, warning-area meaning and changes over time, level mapping and complete-snapshot scope |
| Riverine flood | River/catchment and warning-area applicability to Southbank, level mapping, lifecycle and complete-snapshot scope |
| Flash flood | Confirm that this is a distinct supported product; validate identifiers, level mapping, lifecycle, warning geography and complete-snapshot scope |

For every candidate, verify access and use rights individually and retain the enabled-product coverage definition. Observing riverine flood records under `Met` does not establish availability or completeness for the other candidates. A product absent from a sample stays unverified rather than being treated as warning-free.

### Attribution acceptance

Every VicEmergency warning presentation must include **State of Victoria**, a working link to the [EMV emergency-data notice](https://www.emv.vic.gov.au/responsibilities/victorias-warning-system/emergency-data), and a labelled last-feed-update-received date/time with timezone. Verify all three requirements in CITY-02, including stale/error and replay views that still display warnings. Synthetic demonstrations label the value as a fixture receipt time.

For this application, the last-feed-update-received time is the completion time of the latest successful capture (response received, stored and validated), including captures whose bytes are unchanged. It is distinct from warning issue/update times and does not create a new domain revision or warning-change event. This defines receipt-time handling; it does not reinterpret the provider's warning timestamps.

Preserve this completion time in the accepted capture/manifest and carry it through projection and cache. A new successful capture of identical bytes advances receipt time with a new capture ID and the same payload hash; failed fetches, storage/validation failures, cache rendering and offline replay do not. Replay uses the original capture completion time, never its execution time. Keep area evaluation time separate.

Track receipt evidence independently of warning-domain changes so an unchanged but successfully refreshed feed can update its receipt display and coverage evaluation. Receipt success alone does not establish source freshness or completeness: provider time, warning validity and the verified snapshot contract still apply. Coverage changes remain observable under the [area contract](architecture/area-contract.md#conditions-and-coverage), even when no warning-change event is emitted.

### SRC-02 snapshot freshness question

Verify whether VicEmergency exposes a feed-level generation timestamp and what it means. Use a trustworthy feed-level timestamp to assess snapshot age when available; if absent, evaluate receipt time together with verified snapshot completeness. Set the live freshness thresholds through A-04 after cadence evidence. An individual warning may remain valid for hours without a content update; its issue/update age must not by itself make a freshly verified complete snapshot stale. Warning validity, snapshot freshness and receipt evidence remain separate checks.

### Modelled weather access

Open-Meteo service access and data licensing are separate considerations. Verify current request accounting/limits for the selected query, application eligibility, required credits and stored-output use against its official terms. Keep model identity, units and effective times; receiving model data cannot make warning coverage current. Follow ADR 0005 for informational readings and warning severity; do not apply VicEmergency levels to BOM.

## Map context sources

Status: direction accepted in [ADR 0011](adr/0011-southbank-building-massing.md) on 6 October 2026; none enabled until its MAP item verifies the source and records a fixture manifest. These sources shape the 3D and animated presentation only. None is an input to area membership, conditions, coverage, warning applicability, planning matching or routing. Each is retained as a reviewed static fixture with a manifest; none is polled.

### Building massing

| Field | Record |
| --- | --- |
| Product | City of Melbourne **2023 Building Footprints**, dataset ID `2023-building-footprints`, [catalogue page](https://data.melbourne.vic.gov.au/explore/dataset/2023-building-footprints/) |
| Access | Public Opendatasoft API; no credentials. Exports filtered with `intersects(geo_shape, …)` against the retained Southbank boundary |
| Licence and attribution | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Credit City of Melbourne and the dataset, link the licence, and state the modifications (filtered to Southbank, `Structure` only, properties reduced, heights converted to relative values, coordinates rounded) |
| Content | Footprint polygons where walls meet the ground or podium, stacked for podiums, towers and setbacks. Fields used: `structure_id`, `footprint_type`, `footprint_min_elevation`, `footprint_max_elevation`, `structure_min_elevation`, `date_captured`. Elevations use the Australian Height Datum |
| Time semantics | Catalogue metadata modified 10 April 2024; polygon `date_captured` ranges from 28 May 2018 to 11 May 2023. Neither date is an observation of current construction; DAM developments completed after capture can be absent |
| Southbank coverage (6 October 2026) | 1,189 intersecting polygons for 387 structures: Structure 1,108, Tram Stop 34, Bridge 30, Jetty 15, Toilet 1, Tunnel 1. No missing heights. Unfiltered export about 1.49 MB |
| Use | Visual context only. Never an input to area membership, conditions, coverage, warning applicability, planning matching or routing |
| Retention | Static fixture retained in the repository with its manifest. Refresh only through a reviewed change; no polling or live capture |

Retained fixtures record the export query, retrieval date, source response SHA-256, fixture SHA-256, included and rejected counts and the modification note. Recheck the licence and field definitions when refreshing the fixture.

### Tram track geometry (MAP-02)

| Field | Record |
| --- | --- |
| Product | DTP [GTFS Schedule](https://opendata.transport.vic.gov.au/dataset/gtfs-schedule), tram feed `shapes.txt`, linked through `trips.txt` to route IDs. Already the static companion selected in [ADR 0002](adr/0002-southbank-tram-pilot.md) |
| Access and licence | Public download, no credentials; CC BY 4.0. Catalogue checked 6 October 2026: one ZIP of about 250 MB covering trains, buses and trams, last modified 4 October 2026 |
| Use | Track lines for tram heading and interpolation between consecutive observed positions; replaces the illustrative fixture tracks. Never used to infer positions beyond the latest observation |
| To verify before MAP-02 | Tram shapes present for the routes crossing Southbank; shape-to-route/trip linkage and direction; shape identity stability across releases; coordinate precision; matching tolerance between observed points and shapes; size after clipping to Southbank; identifiers and manifest required by the [proposed animation input contract](architecture/tram-animation-input-contract.md) |
| Retention | Clipped Southbank shapes retained with the release date, source ZIP SHA-256 and route/shape IDs. The full ZIP is not committed |

### Road centrelines (MAP-05)

| Field | Record |
| --- | --- |
| Product | [Vicmap Transport Road Line](https://discover.data.vic.gov.au/dataset/vicmap-transport-road-line), Department of Transport and Planning |
| Access and licence | Public download (SHP, GDB and other formats; a REST API is listed separately), no credentials; CC BY 4.0. Catalogue checked 6 October 2026, metadata modified 3 October 2026 |
| Use | Paths for clearly labelled simulated traffic only. No speed, volume, congestion or travel-time meaning |
| To verify before MAP-05 | Road classes to include, one-way/direction attributes, coordinate system and conversion to WGS84, size after clipping to Southbank, required attribution wording |
| Alternative | OpenStreetMap roads are licensed under ODbL, whose share-alike obligations need separate review; not proposed |

### 3D model assets (MAP-02, MAP-04)

Tram, crane and scaffold models must be created for the project or come from an identified source whose licence allows public display and modification, preferably CC0 or CC BY. Record each model's source, author, licence, attribution text, file SHA-256 and any modifications. Do not use models extracted from games, commercial viewers or unlicensed downloads. A tram model is a generic representation and must not imply a specific operator's livery unless its use is permitted.

## Common geography and time

Southbank means the provider's **CLUE small area**, not an interchangeable suburb or postcode. The [comparison](evidence/src-01-source-feasibility.md#geography-measured) supports static transport/planning overlap. Weather overlap still needs a permitted warning representation and an agreed precision rule; a state RSS entry cannot by itself establish a Southbank impact.

Store boundary revision/hash and dataset identity with spatial results. Keep capture time, provider publication time and event validity distinct. DAM completion year is not its observation timestamp, and CLUE metadata modification is not proof of a geometry update. Unsupported or stale inputs remain explicit rather than becoming normal/zero.

## Enablement record

Before activating each source, record:

1. Product/feed identity, canonical URL, access method and secret reference.
2. Licence/version, attribution text, allowed display/derivative/redistribution uses and accepted retention duration.
3. Spatial coverage and exclusions, time semantics and expected refresh; for warnings, complete-snapshot scope, withdrawal/cancellation rules and the meaning of an empty result.
4. Request quotas, shared scope, timeout/size limits and bounded retry behavior.
5. Supported identifiers and permitted test samples, with validation/rejection and freshness policies.
6. Bounded integration result, first retained object/manifest retrieval and restart behavior.
7. Architect acceptance, verification date and triggers for rechecking changed terms/schema/coverage.

Credentials remain outside Git. Use synthetic public fixtures until any real sample's redistribution conditions have been met.

## Collection timing

Resolve source policy and A-06 early so CLOUD-01 can collect transport in phase 1 and weather/planning in phase 2. Track first retained date and capture gaps separately from feature milestones. Collection may begin after its own source/capture/cloud gates pass without waiting for a hosted API or warehouse. A-03 defines capture identity and manifests before storage is provisioned.

# Source register

Reviewed: 4 October 2026. This register owns source evidence and enablement requirements. Integration progress is in the [delivery plan](delivery-plan.md). Measurements and official references are in the [SRC-01 evidence](evidence/src-01-source-feasibility.md).

## Source scope and enablement gates

The architect selected **Southbank CLUE** and **Yarra Trams positions, trip updates and alerts**, with compatible static GTFS, in [ADR 0002](adr/0002-southbank-tram-pilot.md). Source selection does not itself enable live capture.

| Domain                    | Product                                                                                                                                                                          | Verified evidence                                                                                                                                                             | Before live enablement                                                                                                                                                       |
| ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Transport                 | [DTP GTFS-Realtime](https://opendata.transport.vic.gov.au/dataset/gtfs-realtime), Yarra Trams, plus [GTFS Schedule](https://opendata.transport.vic.gov.au/dataset/gtfs-schedule) | Three Tram feeds; CC BY 4.0; published authentication/quota discrepancy documented in SRC-01                                                                                  | Verify active header and quota scope, supply server-side credentials, test static/realtime IDs, position freshness and alert coverage; accept attribution and capture policy |
| Weather & Hazards         | BOM severe-weather products IDV21037 and IDV21038, candidate first slice                                                                                                         | [Warning guide](https://www.bom.gov.au/catalogue/Bureau_of_Meteorology_warning_products_user_guide.pdf) documents concurrent products, CAP, lifecycle and district references | Accept product scope/precision; establish permission for public display, derivatives and retention; verify samples, identifiers, expiry and spatial applicability            |
| Planning & Infrastructure | [City of Melbourne Development Activity Monitor](https://data.melbourne.vic.gov.au/explore/dataset/development-activity-monitor/)                                                | Public API, CC BY 4.0, monthly cadence; 128 Southbank records; all pilot points matched named polygons in the inspected snapshot                                              | Accept this planning slice and retention duration; define identity/change/deletion handling and attribution; verify capture/retrieval                                        |
| Spatial foundation        | [CLUE small areas](https://data.melbourne.vic.gov.au/explore/dataset/small-areas-for-census-of-land-use-and-employment-clue/)                                                    | Southbank selected; CC BY 4.0; boundary geometry and publication timestamps inspected                                                                                         | AREA-01 defines internal ID, version/hash, coordinate validation, boundary-edge and catchment rules                                                                          |
| Road incidents/works      | Additional official source to evaluate separately                                                                                                                                | GTFS and DAM do not establish comprehensive road incident or works coverage                                                                                                   | Verify access, spatial/temporal fields and ownership before adding a road layer                                                                                              |

The warning slice does not cover every hazard. Heat, flood and weather observations require additional product evaluation. Preserve official severity and source links; an application status is not official emergency guidance.

## Access and use policy

[DTP and municipal CC BY 4.0 licensing](https://creativecommons.org/licenses/by/4.0/) permits sharing and adaptation subject to attribution, licence links and change notices. Proposed credits identify the Department of Transport and Planning, Victoria, or City of Melbourne, the specific dataset and modifications made by UrbanPulse. Preserve source notices in any published sample. The project must still choose retention duration, storage budget and access controls; those values are not implied by the licence.

BOM's [default terms](https://www.bom.gov.au/copyright) and [RSS terms](https://www.bom.gov.au/rss/) do not establish the required public application/archive rights for the candidate warning products. Obtain product-specific terms or permission before those uses. Use synthetic warning fixtures in the meantime; no BOM content was captured for public fixtures during SRC-01.

Transport collection metadata and Tram OpenAPI definitions disagree on authentication and quotas. Keep that discrepancy visible until resolved. A bounded successful probe must confirm the active contract; production polling must share its budget across workers and retries. Map tile access and attribution are a separate A-02 decision.

## Common geography and time

Southbank means the provider's **CLUE small area**, not an interchangeable suburb or postcode. The [comparison](evidence/src-01-source-feasibility.md#geography-measured) supports static transport/planning overlap. Weather overlap still needs a permitted warning representation and an agreed precision rule; a state RSS entry cannot by itself establish a Southbank impact.

Store boundary revision/hash and dataset identity with spatial results. Keep capture time, provider publication time and event validity distinct. DAM completion year is not its observation timestamp, and CLUE metadata modification is not proof of a geometry update. Unsupported or stale inputs remain explicit rather than becoming normal/zero.

## Enablement record

Before activating each source, record:

1. Product/feed identity, canonical URL, access method and secret reference.
2. Licence/version, attribution text, allowed display/derivative/redistribution uses and accepted retention duration.
3. Spatial coverage and exclusions, time semantics and expected refresh.
4. Request quotas, shared scope, timeout/size limits and bounded retry behavior.
5. Supported identifiers and permitted test samples, with validation/rejection and freshness policies.
6. Bounded integration result, first retained object/manifest retrieval and restart behavior.
7. Architect acceptance, verification date and triggers for rechecking changed terms/schema/coverage.

Credentials remain outside Git. Use synthetic public fixtures until any real sample's redistribution conditions have been met.

## Collection timing

Resolve source policy and A-06 early so CLOUD-01 can collect transport in phase 1 and weather/planning in phase 2. Track first retained date and capture gaps separately from feature milestones. Collection may begin after its own source/capture/cloud gates pass without waiting for a hosted API or warehouse. A-03 defines capture identity and manifests before storage is provisioned.

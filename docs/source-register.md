# Candidate source register

Reviewed: 4 October 2026. This register owns source evidence and enablement requirements. Integration progress is in the [delivery plan](delivery-plan.md).

## Candidate coverage

| Domain                    | Official candidate                                                                                                                | Evidence and constraint                                                                                                                                                                                                                                    | Still to verify                                                                                                                                                                             |
| ------------------------- | --------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Transport                 | [Transport Victoria GTFS-Realtime](https://opendata.transport.vic.gov.au/dataset/gtfs-realtime) and matching static feeds         | The collection lists trip updates, service alerts and vehicle positions; availability differs by feed. Compare position-capable feeds explicitly for the moving-map experience. Published Metro/Tram/Bus rate limits must shape polling and retry budgets. | Selected feed credentials, exact per-key/feed quota scope, compatible static/vehicle IDs, position timestamps/coordinates, observed cadence, permitted capture/redistribution and retention |
| Weather & Hazards         | [BOM data feeds](https://www.bom.gov.au/catalogue/data-feeds.shtml)                                                               | Official catalog lists forecasts, observations and warning products. Product-specific access and use conditions apply.                                                                                                                                     | Exact Victorian warning product, access method, licence/use terms, stable IDs, affected geography, issue/update/cancel/expiry semantics and availability                                    |
| Planning & Infrastructure | [City of Melbourne Development Activity Monitor](https://data.melbourne.vic.gov.au/explore/dataset/development-activity-monitor/) | Candidate development data for the municipality, with a slower update cadence. Pilot candidates are CBD, Southbank and Carlton. Richmond is in the City of Yarra and requires another planning source.                                                     | API/schema, current refresh and licence terms, statuses, spatial completeness, historical snapshots and a useful common pilot area                                                          |
| Spatial foundation        | Official versioned area boundaries, dataset to select                                                                             | Shared geography is necessary to combine domains consistently.                                                                                                                                                                                             | Licence, geographic unit, stable IDs/version policy, coordinate system and attribution                                                                                                      |
| Road incidents/works      | Separate official source, to identify                                                                                             | Transport GTFS availability does not establish comprehensive road incident coverage.                                                                                                                                                                       | Access, reliability, spatial/temporal fields and ownership under the agreed domain model                                                                                                    |

Storm, flood, heat and other hazards are intended domain capabilities, not a claim that one BOM feed covers every disaster. Preserve official severity and link to the original warning; an application status is not official emergency guidance.

## Enablement record

For every selected source, record:

1. Product/feed identity, canonical URL, access method and secret reference.
2. Licence/version, attribution text, allowed use, redistribution and retention evidence.
3. Spatial coverage and exclusions, time semantics and refresh expectations.
4. Request quotas, retry instructions, timeout/size bounds and shared budget scope.
5. Schema examples and supported IDs; whether retained samples can be used in public tests.
6. Validation/rejection policy, freshness thresholds and outage behavior.
7. Accepted decision, verification date, bounded integration result and next review trigger.

Never commit provider credentials or payloads without verified redistribution permission. Prefer synthetic public fixtures while access is unresolved.

## Common-geography gate

Compare published boundaries for Southbank, CBD and Carlton against all three source domains; Southbank is the demonstration example. Select the useful overlap, or find an additional official planning dataset. An unsupported area must visibly report missing coverage.

The architect must accept the source scope, boundary model and use/retention policy before live implementation. A planning feed updating slowly can still be useful; display its as-of date separately from warning validity and transport freshness.

## Collection timing

Complete source-use and retention decisions early enough for CLOUD-01 to capture transport in phase 1 and add weather/planning in phase 2. Track first retained date, expected refresh, actual capture gaps and recoverable history. The collector can store permitted inputs before the area model or warehouse is ready.

# ADR 0004: Southbank fixture map and spatial policy

Date: 2026-10-05

Decision: use the agreed CITY-01 fixture scope. Live-source policies remain separate.

## Context

The first city view needs reproducible moving observations, an explainable area panel and genuine spatial membership. It must work without provider credentials or an external map account. [ADR 0002](0002-southbank-tram-pilot.md) chooses the Southbank CLUE pilot; [ADR 0003](0003-cloudevents-and-area-conditions.md) separates conditions from coverage.

## Decision

- Use stable area ID `au-vic-melbourne-clue-southbank`, WGS84 longitude/latitude and PostGIS SRID 4326.
- Use `ST_Covers`: points on the boundary are included; no walking buffer. Service impact belongs to the affected stop independently of vehicle movement.
- Retain the official Southbank geometry with attribution and source-response hash. Hash sorted-key compact JSON geometry as `sorted-keys-json-v1`; metadata changes do not change the boundary revision.
- Use MapLibre with a local outline, synthetic tram icons and optional illustrative tracks. The white/grey interface uses a text-only wordmark. Track geometry is decorative fixture data, never an input to spatial membership or routing. No external tiles, fonts or styles. Marker and keyboard-list selection share the same vehicle identity.
- Use a fixed, request-local fixture clock. Position age below 120 seconds is current; age 120–299 seconds is stale; age 300 seconds or more remains in the last-known list only. Missing/future observation time is unknown. These values apply only to `southbank-fixture-v1`.
- Keep transport service coverage, weather warnings and planning profile separate. Absent weather prevents Normal; an applicable transport disruption gives Degraded. Positions themselves are not a health signal.

A buffered catchment would change the area's meaning. A public basemap would introduce provider and attribution choices. Both can be added through later decisions; neither is needed for this fixture acceptance.

## Consequences

The API reconstructs a bounded projection from a retained fixture bundle and queries real PostGIS. Replay can demonstrate duplicate, old, conflicting and invalid events without a persistent consumer ledger. No database schema or migration is introduced. The content-addressed bundle is a fixture storage adapter, not the proposed production capture ledger.

Live freshness, warning geometry, basemap delivery and capture retention require their own evidence and decisions. See the [area contract](../architecture/area-contract.md), [walkthrough](../demos/city-01.md) and [delivery plan](../delivery-plan.md).

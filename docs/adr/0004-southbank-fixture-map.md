# ADR 0004: Southbank fixture map and spatial policy

Date: 2026-10-05

Status: **Proposed — awaiting explicit acceptance by the project architect.**

The implementation is a reviewable fixture proposal. Authorisation to build CITY-01 does not by itself accept its point-edge/no-buffer rule, internal identity, no-basemap choice or 120/300-second freshness thresholds. Accepted pilot and condition/coverage decisions remain in ADR 0002 and ADR 0003.

## Context

The first city view needs reproducible moving observations, an explainable area panel and genuine spatial membership. It must work without provider credentials or an external map account. [ADR 0002](0002-southbank-tram-pilot.md) chooses the Southbank CLUE pilot; [ADR 0003](0003-cloudevents-and-area-conditions.md) separates conditions from coverage.

## Proposed decision

- Use stable area ID `au-vic-melbourne-clue-southbank`, WGS84 longitude/latitude and PostGIS SRID 4326.
- Use `ST_Covers`: points on the boundary are included; no walking buffer. Service impact belongs to the affected stop independently of vehicle movement.
- Retain the official Southbank geometry with attribution and source-response hash. Hash sorted-key compact JSON geometry as `sorted-keys-json-v1`; metadata changes do not change the boundary revision.
- Use MapLibre with a local outline, synthetic tram icons and optional illustrative tracks. The white/grey interface uses a text-only wordmark. Track geometry is decorative fixture data, never an input to spatial membership or routing. No external tiles, fonts or styles. Marker and keyboard-list selection share the same vehicle identity.
- Use a fixed, request-local fixture clock. Position age below 120 seconds is current; age 120–299 seconds is stale; age 300 seconds or more remains in the last-known list only. Missing/future observation time is unknown. These values apply only to `southbank-fixture-v1`.
- Keep transport service coverage, weather warnings and planning profile separate. Absent weather prevents Normal; an applicable transport disruption gives Degraded. Positions themselves are not a health signal.

A buffered catchment would change the area's meaning. A public basemap would introduce provider and attribution choices. Both can be added through later decisions; neither is needed to review this fixture proposal.

## Consequences

The API pins a verified fixture bundle for the service lifetime and reconstructs time-dependent projections per request. Service changes are captured frames; only records received by the selected clock contribute. The outage fixture loses transport access at 90 seconds, after the 60-second interruption but before its 180-second resolution. Real PostGIS results are memoized only for identical boundary/point inputs. Replay can demonstrate duplicate, old, conflicting and invalid events without a persistent consumer ledger. No database schema or migration is introduced. The content-addressed bundle is a fixture storage adapter, not the proposed production capture ledger.

Live freshness, warning geometry, basemap delivery and capture retention require their own evidence and decisions. See the [area contract](../architecture/area-contract.md), [walkthrough](../demos/city-01.md) and [delivery plan](../delivery-plan.md).


## Service freshness limitation

CITY-01 does not implement a service-status TTL. At 360 seconds the clear frame received at 180 seconds is still labelled `current`. In this authored fixture, that label denotes the latest complete service snapshot, not a verified freshness guarantee for a live feed. Position age thresholds do not apply to service coverage. Outage still produces `error`, and an unresolved interruption remains Degraded regardless of coverage.

Before live transport enablement, the architect must select and version service freshness thresholds using measured alert/update cadence. Test the exact stale transition, missing timestamps, repeated fetches and unresolved facts before treating `current` as fresh provider coverage. The independent source-observation time is retained in `service_evidence.observed_at` so this limitation is inspectable.

Within the single-stop fixture, consecutive disrupted frames update one episode: its ID and effective start come from the first disrupted frame, while reason text and provenance follow the latest received frame. A received clear frame ends it; a subsequent interruption starts a new episode. This is not a contract for correlating multiple live disruptions.

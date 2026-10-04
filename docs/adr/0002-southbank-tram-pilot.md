# ADR 0002: Southbank CLUE pilot with tram positions and service status

Status: accepted by the project architect on 4 October 2026 for pilot geography and initial transport scope. Complements [ADR 0001](0001-city-intelligence-scope.md).

## Context

The first area must support the integrated transport, weather and planning story. [SRC-01 evidence](../evidence/src-01-source-feasibility.md) compared Southbank, Melbourne (CBD) and Carlton using official CLUE boundaries, static transport points and development records. Southbank provides a compact demonstration, with 24 tram stop records and 128 development records in the inspected snapshot. Weather product access and precise applicability still need verification.

## Decision

Use the **Southbank CLUE small area** as the first pilot, labelled as a CLUE area rather than a gazetted suburb or postcode. Select the provider's Southbank geometry and preserve its source/version provenance. AREA-01 defines the internal identifier, boundary version, edge rules and accessible map experience.

Use **Yarra Trams vehicle positions, trip updates and service alerts**, together with compatible static GTFS, for the first transport slice. Positions support the moving map; updates and alerts supply service context. Begin with synthetic fixtures, then enable live inputs after the source gates pass. A location observation alone does not establish a delay or disruption.

## Alternatives

- Melbourne (CBD): more stop/development records and transport modes; retain as an expansion option.
- Carlton: another supported static-data candidate; not the initial pilot.
- Status-only transport: fewer position-specific requirements, but omits the selected moving-map experience.
- Metro train first: better aligned with a different pilot; the inspected Southbank polygon contains no Metro train stop points.

## Consequences and decision boundary

Keep Weather & Hazards and Planning & Infrastructure in the city MVP. This selection does not narrow the product to transport. Build position freshness, invalid/missing coordinates and synthetic playback cases into the transport contract and tests.

This decision accepts geography and transport scope, not live-source enablement. The official authentication/quota discrepancy, schedule joins, sample validation and use/retention policy remain gates. Planning source acceptance and the exact BOM product/precision need their own review. Map tiles under A-02 remain undecided. A-03/A-04 retain identity, boundary-edge semantics, event contracts and status rules; A-06 retains cloud host, region, identities and budget.

If approved weather access cannot support area-level interpretation, return to the architect with the measured limitation and options before changing the weather promise or pilot. Revisit this ADR if the chosen boundary or transport mode changes.

# ADR 0006: Weather fixture spatial applicability and freshness

Date: 2026-10-05

Status: **Accepted by the project architect** for the CITY-02 fixture policies below.

## Decision

A warning polygon applies to Southbank when the polygon interiors overlap with positive area. Mere edge or vertex contact does not count. Use valid WGS84 Polygon/MultiPolygon geometry and PostGIS `ST_Relate(area, warning, '2********')`; containment, holes and disconnected components retain their GeoJSON meaning. Missing or invalid warning geometry leaves applicability unknown. Never infer observed hazard impact from a warning intersection.

The synthetic replay uses explicit complete/incomplete snapshot declarations and authored stale/error checkpoints. It does not select a numerical live TTL. Snapshot completeness must name every pilot warning product; a recent receipt alone does not establish coverage. Unknown products, levels, geography and unresolved omissions prevent a complete-coverage claim. Expiry removes the adverse fact but cannot repair an incomplete snapshot or source failure.

These choices extend the accepted source and severity policy in [ADR 0005](0005-weather-source-policy.md). Live spatial evidence and freshness thresholds remain SRC-02/A-04 work. The proposed transport/fixture-map decisions in ADR 0004 are not accepted by this decision.

## Alternatives and consequences

Counting all intersections would include edge-only contacts. A fixed freshness timer now would guess at provider cadence before source verification. The chosen approach gives reproducible boundary and lifecycle tests while reserving live feed semantics for measured evidence.

Keep the latest successful validated capture completion time independently from warning revisions. An unchanged recapture can advance receipt time without publishing a warning change. Offline replay uses retained times. A failure or coverage checkpoint cannot advance them.

[Walkthrough](../demos/city-02.md) and [contract](../architecture/weather-fixture-contract.md) define the executable fixture and its limits.

# ADR 0011: Southbank building massing context

Date: 2026-10-06

Status: **Proposed for project architect review.** Implementation (MAP-01) follows DEMO-01 and waits for an explicit decision.

## Problem

The accepted [ADR 0004](0004-southbank-fixture-map.md) map shows the Southbank outline, synthetic trams, warning areas and development points on a plain background. Reviewers unfamiliar with Southbank have little visual reference for where these observations sit. A 3D view of real building massing would provide that context, but it introduces a new data source, a new map layer and a risk of drawing attention away from area conditions and coverage.

MapLibre GL, already in use, renders pitched views and `fill-extrusion` layers. No new rendering dependency is needed for building massing. Terrain is out of scope: Southbank is flat and a terrain layer would add a data source without adding meaning.

## Options

| Option | Data and rendering | Trade-off |
| --- | --- | --- |
| **A: retained City of Melbourne footprints (recommended)** | [2023 Building Footprints](https://data.melbourne.vic.gov.au/explore/dataset/2023-building-footprints/), filtered to structures intersecting Southbank, served as a local static layer and extruded by MapLibre | Official municipal source, CC BY 4.0, explicit heights and stacked podium/tower components; no external request at runtime. Capture dates are 2018–2023, so recent construction is missing. |
| B: buildings from a basemap vector-tile provider | Provider tiles with building heights, chosen under A-02 | Brings streets and labels as well, but adds a provider account, runtime requests, terms and attribution, and building heights of uneven completeness. Depends on the still-open A-02 basemap decision. |
| C: City of Melbourne 3D textured mesh or point cloud | [Photomesh](https://data.melbourne.vic.gov.au/explore/dataset/city-of-melbourne-3d-textured-mesh-photomesh-2020/) or point cloud via a 3D Tiles renderer | Highest visual fidelity, but large data, a new rendering stack and weak mobile performance for a fixture demo. |

Option A keeps the map self-contained, as ADR 0004 requires for the fixture, and does not pre-empt A-02. B or C can be evaluated later when a public basemap or richer 3D view has concrete requirements.

## Proposed decision: option A

### Source and selection

Use the City of Melbourne **2023 Building Footprints** dataset (dataset ID `2023-building-footprints`, CC BY 4.0). Select footprint polygons whose geometry intersects the accepted Southbank CLUE boundary revision, keeping whole polygons rather than clipping them at the boundary.

Measured on 6 October 2026 through the dataset's public API, using the retained Southbank boundary:

| Measure | Value |
| --- | --- |
| Intersecting footprint polygons | 1,189 (387 distinct structures; 209 structures have stacked components) |
| Footprint types | Structure 1,108; Tram Stop 34; Bridge 30; Jetty 15; Toilet 1; Tunnel 1 |
| Polygon `date_captured` | 907 from 2018-05-28, 185 from 2022-01-20, 95 from 2023-05-11 |
| Structure height (`structure_extrusion`) | Median 16.9 m; maximum 316.5 m; no missing values |
| Unfiltered GeoJSON export | About 1.49 MB, about 30,300 vertices |

Include only `footprint_type = Structure` in the first layer. Bridges, tunnels and jetties are not ground-based extrusions, and real tram-stop shapes would be confused with the synthetic tram scenario. Each excluded type can be added later with its own rendering rule.

### Heights

Footprints are stacked components measured against the Australian Height Datum. Render each polygon relative to its own structure's base:

- extrusion base = `footprint_min_elevation` − `structure_min_elevation`
- extrusion top = `footprint_max_elevation` − `structure_min_elevation`

Reject a polygon whose base is negative, whose top is not above its base, or whose elevation fields are missing, and record the rejection count in the fixture manifest. Do not substitute a default height.

### Context only

Building massing is visual context. It never contributes to area membership, conditions, coverage, warning applicability, planning matching or routing. Matching DAM development points to footprints, or highlighting a development's building, needs a separate spatial rule and decision. Warning polygons stay flat; extruding them would read as severity or physical extent.

### Retained fixture

Retain the filtered layer in the repository as a versioned fixture, like the Southbank boundary:

- keep only `structure_id`, `footprint_type`, the computed base and top heights and `date_captured`;
- round coordinates to 6 decimal places (about 0.1 m) and apply no geometric simplification initially;
- record the dataset ID, export query, retrieval date, source response SHA-256, licence, fixture SHA-256, polygon and rejection counts, and the modification note.

Serve the layer as a same-origin static asset with a content hash in its file name, so browsers can cache it immutably and the map makes no external request. Add it explicitly to the web build-context allowlist. Refreshing it is a reviewed change with a new hash; there is no polling.

### Presentation

- 2D remains the default view. A control switches to a pitched, rotatable 3D view; `prefers-reduced-motion` disables camera animation.
- Buildings use a neutral, partly transparent fill so tram markers, the Southbank outline and warning areas stay legible above them. HTML markers remain screen-aligned.
- The layer can be hidden like the existing layers. The keyboard list remains the primary accessible path, and the existing map-unavailable message covers WebGL failure.
- The map credit reads: *Building footprints: City of Melbourne, CC BY 4.0; captured 2018–2023; filtered and converted by UrbanPulse.* State that recent construction may be missing.

## Acceptance cases

- Given the retained fixture, the layer's hash, counts and provenance match its manifest, and only `Structure` footprints intersecting the accepted Southbank revision are included.
- Given a stacked podium and tower, rendered component bases and tops follow the relative-height rule; a polygon with invalid elevations is excluded and counted, never given a default height.
- Given the 3D view, trams, the boundary, warnings and development markers remain visible and selectable; switching layers or views does not change any API request or area result.
- Given browser tests, enabling 3D makes no request outside the application origin, the building credit is visible, and keyboard selection still works.
- Given reduced motion or a WebGL failure, the map remains usable or shows the existing fallback.
- Measure fixture size and render time on desktop and mobile emulation before acceptance; simplify geometry only if those measurements require it.

## Decisions requested

1. Accept option A, or choose B or C.
2. Confirm the first layer includes `Structure` only.
3. Confirm the retained-fixture approach and the attribution wording.

Accepting A does not decide A-02's public basemap, live data sources or DAM-to-building matching. See the [source register](../source-register.md#building-massing-context) and [delivery plan](../delivery-plan.md).

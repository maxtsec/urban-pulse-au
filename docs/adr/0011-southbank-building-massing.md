# ADR 0011: Southbank 3D massing and animated map context

Date: 2026-10-06

Status: **Accepted by the project architect on 2026-10-06** for building option A, MapLibre with deck.gl, the five animation classes and their rules, MAP-05 simulated traffic in scope, and a `Structure`-only first building layer. Implementation (MAP-01 to MAP-05) follows DEMO-01; each item still needs its own source/asset records and review.

## Problem

The accepted [ADR 0004](0004-southbank-fixture-map.md) map shows the Southbank outline, synthetic trams, warning areas and development points on a plain background. The target presentation is an animated 3D city view:

- transparent buildings with real heights;
- solid 3D trams moving along their tracks;
- translucent simulated road traffic;
- weather animation;
- construction animation at development sites.

This needs a building data source, a rendering approach for models and animated paths, and rules that keep animation from being mistaken for observed data. The map and the area panel must still lead with conditions, coverage and reasons.

Terrain is out of scope: Southbank is flat and a terrain layer would add a data source without adding meaning.

## Building source options

| Option | Appearance | Fit for transparency and animation | Trade-off |
| --- | --- | --- | --- |
| **A: retained City of Melbourne footprints (recommended)** | Plain massing blocks with surveyed heights; podium and tower steps visible | Good: per-layer colour and opacity, clean background for moving objects | Official, CC BY 4.0, local; no streets or labels; capture dates 2018–2023 miss recent construction |
| B: basemap vector-tile buildings | Street map with roads, water, parks, labels and extruded blocks | Usable, but a busier background | Needs the open A-02 provider decision, an account, runtime requests and provider terms; heights are often estimated |
| C: City of Melbourne 3D textured mesh | Photorealistic aerial mesh, similar to a globe viewer | Poor: the mesh cannot be made usefully transparent or recoloured, and animation over it is hard to read | Gigabyte-scale data streamed as 3D Tiles; slow on mobile |

A gives the clearest base for the requested effects and keeps the map self-contained, as ADR 0004 requires. B can be layered underneath later if A-02 selects a basemap. C remains a possible separate photorealistic mode.

## Rendering options

| Option | Capability | Trade-off |
| --- | --- | --- |
| MapLibre only | Pitched view and `fill-extrusion` buildings | No glTF models, animated trails or particles without custom code |
| **MapLibre with an interleaved deck.gl overlay (recommended)** | Extruded polygons with transparency, glTF models (`ScenegraphLayer`), animated trips (`TripsLayer`), later 3D Tiles (`Tile3DLayer`) | A new primary frontend dependency (MIT licence) and a larger bundle; layers must share MapLibre's camera and depth |
| MapLibre with a Three.js custom layer | Unlimited effects | Most bespoke rendering, picking and accessibility code to own |

The brief lists deck.gl for use "when justified". Moving models, trails and transparent massing are that justification. MapLibre keeps ownership of the camera, the boundary and the existing layers; deck.gl renders the 3D and animated layers in the same view.

## Decision: A with deck.gl

### Building source and selection

Use the City of Melbourne **2023 Building Footprints** dataset (dataset ID `2023-building-footprints`, CC BY 4.0). Select footprint polygons whose geometry intersects the accepted Southbank CLUE boundary revision, keeping whole polygons rather than clipping them at the boundary.

Measured on 6 October 2026 through the dataset's public API, using the retained Southbank boundary:

| Measure | Value |
| --- | --- |
| Intersecting footprint polygons | 1,189 (387 distinct structures; 209 structures have stacked components) |
| Footprint types | Structure 1,108; Tram Stop 34; Bridge 30; Jetty 15; Toilet 1; Tunnel 1 |
| Polygon `date_captured` | 907 from 2018-05-28, 2 from 2020-05-15, 185 from 2022-01-20, 95 from 2023-05-11 |
| Structure height (`structure_extrusion`) | Median 16.9 m; maximum 316.5 m; no missing values |
| Unfiltered GeoJSON export | About 1.49 MB, about 30,300 vertices |

Include only `footprint_type = Structure` in the first layer. Bridges, tunnels and jetties are not ground-based extrusions, and real tram-stop shapes would be confused with the synthetic tram scenario. Each excluded type can be added later with its own rendering rule.

Footprints are stacked components measured against the Australian Height Datum. Render each polygon relative to its own structure's base:

- extrusion base = `footprint_min_elevation` − `structure_min_elevation`
- extrusion top = `footprint_max_elevation` − `structure_min_elevation`

Reject a polygon whose base is negative, whose top is not above its base, or whose elevation fields are missing, and record the rejection count in the fixture manifest. Do not substitute a default height.

Retain the filtered layer in the repository as a versioned fixture: keep only `structure_id`, `footprint_type`, the computed heights and `date_captured`; round coordinates to 6 decimal places (about 0.1 m); record the dataset ID, export query, retrieval date, source and fixture SHA-256, counts and modification note. Serve it as a hashed same-origin static asset, added explicitly to the web build-context allowlist. Refreshing it is a reviewed change; there is no polling.

### Truthful animation

Every animated element belongs to exactly one class, shown in the map legend and in its tooltip:

| Class | Meaning | Elements |
| --- | --- | --- |
| Observed | Drawn at a received record's position or state | Tram at an observed position; warning area; development status |
| Interpolated | Moved between two received observations along known geometry | Tram movement between consecutive positions |
| Modelled | Driven by a provider model, not a measurement | Rain intensity from the modelled reading |
| Simulated | Generated by UrbanPulse with no source data | Road traffic |
| Illustrative | Decorative representation of a recorded status | Construction cranes and activity |

Rules:

- Animation is presentation only. It never changes an API result, condition, coverage, reason or count.
- Motion follows the scenario clock, not wall-clock time. Pausing, scrubbing or rewinding the clock moves every animated element consistently; a paused clock stops observed and interpolated motion.
- Never extrapolate beyond the latest received observation. A stale position stays still and dimmed; an expired position follows the existing last-known rule.
- Every animated layer is a pure function of the scenario clock and the records received at or before it. Seeking directly to a time and playing from the start to the same time produce the same frame. No layer reads a fixture or record received after the clock.
- Each layer is gated by its own input. One input's missing, stale or failed state stops only the animation it drives and is shown with that input's label; it never appears as calm weather, empty roads or a stopped tram network.
- `prefers-reduced-motion`, low-power or narrow mobile views start in a static 2D view; animation is opt-in there.

### Layers

| Layer | Rendering | Data | Rule |
| --- | --- | --- | --- |
| Transparent massing | deck.gl extruded polygons, neutral colour, partial opacity | Building fixture above | Context only; never used for membership, conditions, planning matching or routing |
| 3D trams | glTF model via `ScenegraphLayer`, heading along the track | Observed positions; tram track geometry from DTP GTFS Schedule shapes | Drawn at *t − 30 s* from observations received by *t*; interpolate only between bracketing observations of the same vehicle on its matched shape; otherwise static ([tram display delay](#tram-display-delay)) |
| Simulated traffic | Translucent animated trails via `TripsLayer` | Southbank road centrelines from Vicmap Transport Road Line; deterministic synthetic trips | Separate toggle; always labelled "Simulated traffic, not real"; no speed, volume or congestion claims |
| Weather | Particle rain over the map; flat pulsing outline for active warnings | Modelled reading for rain; warning projection for outlines | Gated separately ([weather gating](#weather-gating)); rain is area-wide from the modelled point value, never street-specific; warnings stay flat because height would read as severity |
| Construction | Small crane or scaffold models at located DAM points | DAM status | Animate only `Under construction`; other statuses use static markers; unlocated developments are not drawn |

#### Tram display delay

Let *t* be the scenario clock. The 3D tram layer may use only position observations whose receipt time is at or before *t*. It draws each vehicle as of the display time *d = t − D*, where *D* is a versioned presentation delay, `tram-display-delay-v1` = 30 seconds, matching the proposed 30-second position cadence.

- If two received observations of the same vehicle on its matched shape have observation times bracketing *d*, interpolate between them along the shape by observation time.
- If *d* is later than the vehicle's latest received observation, hold the model at that observation; never extrapolate.
- If *d* is earlier than the vehicle's first received observation, or an observation lacks an observation time, draw a static model at that observation instead of interpolating.
- Stale and expired rules are evaluated at *t*, as in the list and area panel.

The legend states that animated tram positions are shown 30 seconds behind the scenario clock. The tram list, selection details and API keep showing the latest received observation at *t*. Changing *D* is a versioned presentation change.

#### MAP-02 animation inputs

The current area API exposes only the latest position per vehicle, and the transport event/fixture has no trip identity. MAP-02 first requires an accepted public transport-contract change and trip-complete fixtures linked to a verified GTFS release. The [input proposal](../architecture/tram-animation-input-contract.md) covers that prerequisite, continuous scenario-clock playback over complete bounded windows, display-time trip transitions, revision acceptance and API-placement choices with [payload estimates](../evidence/map-02-animation-payload.md). The clock/query protocol, field format and bounds remain Proposed; merging the document does not accept them. Option B would also require approval to amend this ADR's unchanged-request rule for view toggles.

#### Weather gating

Rain and warning animation use different inputs and fail independently. Warning-feed coverage (`weather.coverage`) never switches rain on or off.

- **Rain** depends only on the modelled reading. Animate rain when a reading has been received at or before *t*, its `valid_at` is at or before *t* and no more than *W* earlier, and its precipitation is above zero. *W* is a versioned presentation window, `modelled-rain-display-v1` = 60 minutes, matching an hourly model step. Intensity scales with precipitation. Without such a reading, show no rain and label the layer "No current modelled reading". A reading with zero precipitation shows no rain and is labelled as a dry modelled reading.
- **Warning outlines** follow warning lifecycle at *t*: active warnings pulse; scheduled, cancelled and expired warnings do not. Unknown or error warning coverage keeps its existing coverage label and does not hide known active warnings, which remain until their received validity ends.

Interpolation, track matching and these display windows are presentation rules owned by Location Intelligence's view model, not new domain facts. Matching DAM points to building footprints remains out of scope and needs its own spatial rule.

### Presentation and accessibility

- 2D remains the default. A control switches to a pitched, rotatable 3D view with animation.
- Tram, development and warning selection keeps working in 3D and stays synchronised with the keyboard lists, which remain the primary accessible path.
- Each animated layer can be hidden. A legend explains the five classes above.
- The existing map-unavailable message covers WebGL failure.
- Credits list City of Melbourne building footprints (CC BY 4.0, captured 2018–2023, filtered and converted, recent construction may be missing), DTP GTFS Schedule and Vicmap Transport (CC BY 4.0), and any third-party model assets.

### Delivery sequence

| ID | Scope | Additional prerequisite |
| --- | --- | --- |
| MAP-01 | deck.gl overlay, 3D view control, transparent massing, legend and credits | Building fixture |
| MAP-02 | 3D tram model and interpolation along GTFS shapes | Accepted transport event/trip metadata and updated fixture; verified GTFS shapes; tram model asset licence; [playback/API contract acceptance](../architecture/tram-animation-input-contract.md) |
| MAP-03 | Weather particles and warning pulse | None beyond existing fixtures |
| MAP-04 | Construction models at DAM points | Model asset licence |
| MAP-05 | Simulated traffic trails | Road-line fixture |

Each item is a separate reviewed PR with its own tests and measurements. MAP-05 is in scope; the other items do not depend on it.

## Acceptance cases

- The building fixture's hash, counts and provenance match its manifest, and only `Structure` footprints intersecting the accepted Southbank revision are included. Invalid elevations are excluded and counted, never defaulted.
- Stacked podium and tower components render with the relative-height rule.
- Switching views or toggling any animated layer does not change any API request or area result.
- With the scenario clock paused, observed and interpolated trams stop; scrubbing backwards moves them backwards. No tram moves past its latest observation; a stale tram is static.
- For several clock values, including one between two fixture position receipts (for example 15 seconds before the next position is received), seeking directly to the time and playing from 0 to it produce identical tram, rain and warning frames, and no record received after the clock is read.
- At *t*, a tram whose next observation has not yet been received is held at its latest received observation as of *t − 30 s*; it begins moving only after that next observation's receipt time.
- Simulated traffic is off when its toggle is off, always carries its label, and appears in no count, condition or coverage.
- Warning-feed outage with a recent non-zero modelled reading: rain animates from the reading, active warnings keep pulsing until their validity ends, and the warning coverage label shows error.
- Current warning coverage with no reading, or with a reading more than 60 minutes old: no rain, labelled "No current modelled reading"; warnings follow their lifecycle.
- A current reading with zero precipitation: no rain, labelled as a dry modelled reading. Scheduled, cancelled and expired warnings never pulse.
- Reduced motion starts static; WebGL failure shows the existing fallback; keyboard selection works in 2D and 3D.
- Enabling 3D and animation makes no request outside the application origin, and all credits are visible.
- Measure bundle size, fixture size, frame rate and memory on desktop and mobile emulation before accepting each MAP item; simplify geometry or reduce particles only if measurements require it.

## Decision record

| Decision | Outcome (2026-10-06) |
| --- | --- |
| Building source | Option A, retained City of Melbourne footprints |
| Rendering stack | MapLibre with an interleaved deck.gl overlay |
| Animation | The five classes and their rules, as written above |
| Simulated traffic | MAP-05 in scope, under the simulated class and its labelling rule |
| First building layer | `Structure` only; other footprint types need their own rendering rule and decision |

This decision does not decide A-02's public basemap, live data sources, DAM-to-building matching or any live-data animation. See the [source register](../source-register.md#map-context-sources) and [delivery plan](../delivery-plan.md).

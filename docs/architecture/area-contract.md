# Southbank area and map contract

CITY-01 fixture identity, point membership, local map and fixture freshness follow [ADR 0004](../adr/0004-southbank-fixture-map.md). A-04 separates conditions from coverage as accepted in [ADR 0003](../adr/0003-cloudevents-and-area-conditions.md); live freshness, warning applicability, required-source completeness and timing targets remain proposals. Southbank CLUE and the tram slice are accepted in [ADR 0002](../adr/0002-southbank-tram-pilot.md). Progress belongs in the [delivery plan](../delivery-plan.md).

## Area identity and geometry

Use the application ID `au-vic-melbourne-clue-southbank`. Keep it stable when the boundary changes. Each published geometry carries its provider dataset, feature name, retrieval time, licence/attribution and a SHA-256 boundary revision. Derive the revision from canonical geometry bytes under a named serialization version; keep the original download hash separately. A metadata edit alone must not create a geometry revision.

Use longitude/latitude GeoJSON and PostGIS SRID 4326. Validate geometry before publishing it; reject empty, invalid or implausible coordinates. Do not repair geometry silently. Boundary changes produce a new area projection version and recompute memberships. Retain earlier raw bundles for replay; the CITY-01 HTTP adapter serves only its current bundle and returns 404 for other revisions.

Accepted point inclusion rule: a point is in scope when the area covers it, including the edge. [PostGIS ST_Covers](https://postgis.net/docs/ST_Covers.html) includes boundary points; it requires valid inputs. Apply no walking buffer in the first pilot. A stop across the river is not automatically a Southbank stop. A later catchment feature must use a separately named/versioned rule.

Position membership describes where a tram was observed. Service-impact membership uses affected stops or routes joined to the compatible static schedule. A vehicle moving outside the polygon does not cancel a route disruption. A disruption with unknown geography remains visible as unlocated evidence and cannot establish area-wide normality.

For polygon warnings, require a positive-area intersection under a documented projection/tolerance policy; merely touching the area boundary must not mark the whole area affected. District-only warnings carry `spatial_precision=district` and explicit district applicability. A state RSS item without usable geography cannot establish a Southbank impact. The warning product/precision decision remains part of SRC-02.

## Map and panel behavior

Start CITY-01 with a local fixture map style: Southbank outline, synthetic tram icons, independently toggleable illustrative tracks and an equivalent keyboard-accessible list. Track geometry is local demo artwork, not a surveyed or provider-derived rail network. Keep external tile requests disabled until the map provider, attribution and key/budget policy are chosen under A-02. This makes the fixture scenario reproducible without a tile account; it does not settle the public basemap choice.

The panel presents current transport/weather facts, planning context and source coverage in separate sections. Each fact exposes source time, validity and an evidence link. Every fixture screen shows a persistent synthetic-data label and a fixed scenario clock. Planning status and snapshot time stay separate from current disruption counts.

Selecting a marker or list item selects the same record. Keyboard controls reach the area selector, layer toggles and list without requiring map gestures. Announce selection and status changes without repeatedly interrupting screen readers on every position refresh. Reduced-motion mode places markers directly at the latest observation; any later animation is a visual transition between observed points, not a claim about an unobserved trajectory.

Accepted fixture freshness policy: position age below 120 seconds is current; from 120 seconds show a stale marker and its last observed time; at 300 seconds remove it from the current-marker layer while retaining it in the last-known list. Missing source time is unknown from the outset. These are deterministic scenario values; live thresholds require cadence evidence and A-04 acceptance. A repeated fetch must not reset age. Invalid points are withheld and counted in quality/coverage evidence.

## Conditions and coverage

Use Normal, Degraded and Unknown conditions, accompanied by reasons and per-input coverage. Code/wire values are lowercase `normal`, `degraded` and `unknown`; the table uses uppercase display labels. Do not emit a numerical health score.

| Evidence at evaluation time | Conditions | Coverage/reasons |
| --- | --- | --- |
| Applicable confirmed transport disruption; weather missing | DEGRADED | Transport reason plus weather unknown |
| No confirmed adverse fact; weather missing | UNKNOWN | Missing weather prevents a normal claim |
| All required current-condition inputs supported, current and complete; no adverse fact | NORMAL | List the inputs and policy version used |
| Warning expires; transport disruption remains | DEGRADED | Remove expired warning reason; retain transport reason |
| A source fails while its unresolved adverse fact remains applicable | DEGRADED | Retain last-known reason, expose stale/error coverage; no recovery from failure alone |
| Sole warning expires while weather access is unavailable | UNKNOWN | Expired warning stops contributing; missing coverage prevents NORMAL |
| Planning volume rises | Unchanged | Update the area profile without inventing a positive/negative score |

Proposed required inputs for an eventual NORMAL claim are transport service status (complete alerts and trip-update coverage for the agreed scope) and the agreed weather warning product coverage. Positions describe map observations, not service health. Planning completeness belongs to the area profile. Phase 1's transport-only fixture must therefore show UNKNOWN overall when weather is absent, even when transport is clear.

An empty response only supports absence when the source contract establishes a successful complete snapshot of the relevant scope. Source time, capture time, projection time and evaluation time remain distinct. The full status/reason/coverage tuple is the externally observable state: changing coverage is meaningful even if conditions remain DEGRADED.

A timer re-evaluates expiry/freshness with no incoming event. Proposed targets remain p95 domain-commit-to-area-commit within 5 seconds and warning-expiry recomputation within 60 seconds under the agreed baseline workload. Catch-up after restart is measured separately. Neither target includes provider delay or browser rendering.

## Query boundary

Use `GET /api/v1/areas/{area_id}` for one bounded snapshot: area/boundary revision, fixture/live mode, projection version, evaluated time, condition reasons, per-domain coverage and planning profile. Serve geometry through a revision-addressed endpoint so UI refreshes do not repeatedly transfer it. Bound position queries to the selected area and an explicit server limit; pagination/truncation must be visible.

Responses reference the applicable source/capture and policy versions. Public API fields expose attribution and provenance identifiers, never raw storage credentials or internal signed URLs. Unknown area IDs return 404; known areas with missing inputs return a valid snapshot with explicit coverage. Database/read-model failure is a service error, not an empty healthy area. The `/api/v1/fixture` smoke route remains separate. The [CITY-01 walkthrough](../demos/city-01.md#storage-and-query-details) defines fixture clock/scenario parameters, version semantics, cap and evidence links.

## Contract review and CITY-01 evidence

1. Apply the accepted fixture ID, versioned boundary and point-edge/no-buffer rule. Review warning precision separately in SRC-02/CITY-02.
2. Rehearse point-inside, exact-edge, outside and invalid-geometry examples against real PostGIS in CITY-01; verify boundary revision changes rebuild memberships.
3. Demonstrate the same selection through keyboard/list and map, with fixture clock, provenance, loading, empty, error and unknown states.
4. Exercise successive, repeated, missing-time and stale positions at the exact threshold boundaries. Compare visible markers and the accessible list.
5. Verify every status-table case with a controlled clock under the accepted A-04 condition/coverage principle, including failure without false recovery and expiry without a new event.

The pure evaluator takes an explicit required-input policy and an evaluation clock. Every adverse fact must belong to that current-condition input set; facts from profile-only or otherwise unselected inputs are rejected. Additional profile coverage can remain visible without affecting conditions. The pilot policy contains transport service and weather warning inputs, not planning or vehicle-position observations; adapters must establish that `current` means supported, fresh and complete for the selected scope. Spatial matching and source freshness are separate responsibilities. Unit tests of the evaluator do not establish those adapter guarantees.

Coverage entries are returned in input-ID order; active reasons are returned in fact-ID order. Reordering the same inputs at the same evaluation time must not create a changed assessment. A fact cannot resolve before its effective start; resolution at the start is allowed and gives an empty active interval. Resolution and expiry endpoints are exclusive.

Fixture acceptance is recorded in ADR 0004; the delivery plan owns completion state. CITY-01 demonstrates the point-based map slice with real PostGIS and browser evidence. Existing pure evaluator tests cover warning expiry cases; spatially applicable weather data and shared cross-domain events require CITY-02/CITY-04 evidence. Live-source proof remains in SRC-02.

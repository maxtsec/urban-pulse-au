# MAP-02 tram animation input contract

Date: 6 October 2026. Status: **Proposed for architect review**. [ADR 0011](../adr/0011-southbank-building-massing.md) already accepts the animation classes, receipt cutoff, 30-second display delay and static fallbacks. The API placement, bounded projection and shape-linkage format below need acceptance before MAP-02 implementation. Delivery status remains in the [delivery plan](../delivery-plan.md).

## Problem and placement

The current area snapshot exposes one latest position per vehicle. It has no observation history, original receipt time or trip/shape linkage. A browser cache cannot reconstruct a vehicle's earlier motion after reload or a direct seek.

| Option | Data path | Trade-off |
| --- | --- | --- |
| **A: additive `tram_animation` in the area snapshot (recommended)** | The existing area request returns current conditions and a bounded animation projection from the same input scope and clock | Atomic alignment and no extra API request when switching 2D/3D; a small bounded addition to every snapshot |
| B: separate animation endpoint | Fetch a bounded projection alongside every area request, independently of view toggles, and verify matching scope/clock | Keeps the area response smaller; adds a request, response coordination and partial-failure handling |

Option A keeps the existing `vehicles`, assessment, coverage and counts unchanged. The Location Intelligence application view model prepares animation inputs from accepted transport history and the pinned shape fixture. Routes serialize the result; React/deck.gl render it. Track matching produces presentation metadata, not domain events, area membership or a position observation. Live provider enablement remains SRC-02 work.

## Proposed wire fields

All timestamps use UTC RFC 3339. Coordinates are finite WGS84 longitude/latitude; distances are metres. Identifiers remain source-scoped. The projection's clock is the parent snapshot's clock, never browser wall time.

| `tram_animation` field | Meaning |
| --- | --- |
| `contract_version` | `tram-animation-input-v1`; version independently of CloudEvents and the software release |
| `scope_id` | Parent `composition.timeline_id`, identifying the captured inputs, scenario policy, boundary and area policy; animation/shape versions are pinned separately below |
| `clock_at`, `display_at` | Snapshot time *t* and presentation time *d = t - 30 seconds* |
| `policy_version` | Accepted `tram-display-delay-v1` |
| `status`, `reason` | `ready` or `unavailable`, with a nullable diagnostic code; animation-only failures do not change an otherwise valid area result |
| `position_input` | `{state, received_at, capture_ids}` for the position feed at *t*. State is `available`, `unknown` or `error`; this is independent of transport service-alert coverage and per-vehicle freshness |
| `max_vehicles`, `vehicles_truncated` | Parent `positions_limit` and `positions_truncated`; currently at most 100 vehicles, in the same order as parent `vehicles` |
| `max_observations_per_vehicle` | Proposed hard cap of **3**, selected by the rule below; at most 300 observations per response with the current vehicle limit |
| `shapes` | Null or `{revision, sha256, url}` for a pinned shape manifest, served as an immutable hashed same-origin static asset |
| `vehicles` | One entry per parent vehicle when ready; empty when unavailable. Each entry has `vehicle_id`, `source`, `latest_observation: {source, event_id}` and `observations` |

Each observation contains:

| Field | Meaning |
| --- | --- |
| `source`, `event_id`, `revision` | Original accepted event identity and revision. `(source, event_id)` identifies the sample; vehicle identity matches the parent entry |
| `capture_ids` | Original capture references, unique and unchanged by redelivery |
| `observed_at` | Provider observation time, nullable; a missing time disables interpolation |
| `received_at` | Original successful application receipt time. For fixtures, `started_at + at_seconds` of the first accepted frame under the scenario policy; for live data, retained receipt evidence from the original capture. Never request time, replay execution time or broker retry time |
| `longitude`, `latitude` | Original observed coordinates; never replaced by the matched track point |
| `shape_match` | `{status, trip_id, service_date, start_time, route_id, direction_id, shape_id, segment_id, distance_m}`. Status is `matched`, `unmatched` or `ambiguous`; absent identifiers/distances are null |

A matched sample names a shape from `shapes.revision` and records an unambiguous trip instance, directed shape segment and distance along that shape. `service_date`/`start_time` distinguish repeated trip instances where required; their absence cannot bridge an ambiguous trip boundary. Nullable GTFS fields stay null. A route ID alone does not establish a unique shape or direction. The [source register](../source-register.md#tram-track-geometry-map-02) owns GTFS release, field and matching-tolerance verification.

The shape manifest records its source ZIP hash/release, fixture hash, coordinate/distance convention, matching algorithm/version and accepted tolerance, plus included/excluded IDs and counts. Each shape has a stable fixture ID, provider `shape_id` and contiguous components identified by `segment_id`. Each component has ordered vertices and monotonically increasing cumulative metre distances measured from the original shape origin. Preserve original sequence/distance offsets when clipping; excluded spans are not new connecting lines. Missing or ambiguous linkage, an out-of-tolerance point, an unknown shape, or unverifiable manifest keeps the vehicle static at its observed coordinate. Existing illustrative fixture tracks are not matching evidence.

For fixtures, `position_input` is derived from the received position-capture prefix and authored outage policy at *t*: no successful input is `unknown`, a successful capture (including empty) is `available`, and an authored failure is `error`. Its receipt/capture references come from that input evidence. Reconstruct this state on seek; do not infer it from service alerts or browser request success. Live source cadence/TTL remains a separately reviewed SRC-02 policy. Motion requires `available` plus valid samples; an outage holds the observed point while freshness continues to age.

## Bounded selection and deterministic rendering

1. Rebuild the eligible transport prefix for this scope and *t*, using the existing scenario receipt cutoff and revision guard. Include original applied position changes only. Duplicate, conflict, rejected and superseded delivery attempts create no new observation or receipt time; an earlier applied observation remains historical input after a later accepted revision.
2. Keep a vehicle's latest continuous trajectory segment: same source/vehicle, trip instance, direction, pinned shape and `segment_id`. A change of linkage, missing time/match, non-increasing observation time or decreasing distance ends interpolation continuity. Do not interpolate across the break; static display remains available.
3. Within that segment, select **A**, the closest observation at or before *d*, and **B**, the closest at or after *d*. Both must have been received by *t*. Include **L**, the latest accepted observation at *t*, for static fallback and freshness consistency. Return the deduplicated union `{A, B, L}` in canonical accepted revision order, at most three records. Include the latest record even when its time or match is unknown.
4. Equal-time candidates follow accepted revision order, never input-array or request order. An exact observation at *d* needs no interpolation. Otherwise interpolate distance between A and B by observation time only when both belong to the same continuous segment and bracket *d*. Derive position and heading from that pinned shape; never interpolate straight across missing shape spans or invent a connecting segment.
5. When no valid bracket exists, use ADR 0011's static fallback: before the first observation in the current segment hold that first observation; after the latest, or when time/match is unavailable, hold the latest observed point. Never extrapolate. Use the parent vehicle's freshness at *t*, retaining its stale dimming and expired visibility rule. A failed position input stops its motion independently of service alerts and weather.
6. Construct this projection from persisted inputs for every requested clock. Do not return full history or require a browser to have visited earlier clocks. The renderer uses the supplied clock/samples and deterministic geometry; it does not read future fixture records, advance receipt times, or animate from wall time.

The observation cap bounds the response, not server work: MAP-02 must measure historical selection/query cost as well as payload size. The implementation must retrieve the required samples without shipping or revalidating an unbounded archive on each frontend frame.

### Clock example

Assume synthetic observations at 0, 30 and 60 seconds, received at those same times on one verified shape, with increasing distances. These are contract examples, not claims about live cadence.

| Clock *t* | Display *d* | Eligible bracket | Frame |
| --- | --- | --- | --- |
| 15 s | -15 s | Only observation 0 received | Static observation 0; never read observation 30 |
| 45 s | 15 s | Observations 0 and 30 | Interpolate halfway by observation time along the shape |
| 59 s | 29 s | Observations 0 and 30 | Interpolate using those observations; observation 60 is absent |
| 75 s | 45 s | Observations 30 and 60 | Interpolate halfway; no dependence on earlier browser visits |

A delayed observation is eligible only after its actual receipt. An unchanged recapture does not make an old position current. A seek to 45 seconds and playback ending at 45 seconds must select identical IDs, receipts, shape references and pose.

## Shape loading and compatibility

The same area query/projection is used in 2D and 3D. View toggles may load local model/shape assets, but do not add or change API requests, clocks or area results. Verify the pinned manifest and matching fixture hash; load only same-origin assets compatible with the ingress CSP. Shape-load or animation-validation failure shows an explicit animation-unavailable/static fallback while preserving the valid city view and accessible list.

The parent snapshot remains authoritative for area membership, current position/freshness, coverage and counts. Earlier samples may be outside Southbank; they are animation context for a currently included vehicle, not additional area members. Optional trip/shape fields in future transport payloads require their own reviewed contract change; this proposal does not claim they already exist. Clients without `tram_animation` continue to use the existing 2D observations.

## MAP-02 acceptance cases

- Direct seek, reload, rewind and playback to the same clock produce identical sample identity/order, timestamps, matches and pose from the same input scope. Later captures and observations are absent before their receipts, including during outage scenarios.
- Test the clock table, exact observation time, a delayed receipt, missing time, non-increasing times, a trip-instance/direction/shape/segment change and a clipped shape gap. Invalid/ambiguous matching holds the observed point rather than guessing a track.
- Duplicate and unchanged recapture attempts preserve original sample/receipt identity. Conflict/rejected/superseded attempts never enter the trajectory. Canonical selection is independent of request and input-array order.
- A long retained history still returns at most three observations per included vehicle and at most the parent vehicle limit, with explicit vehicle truncation. Parent vehicle ordering and latest sample identity remain aligned; samples retained for a bracket cannot be silently removed by a history cutoff.
- Stale/expired positions, failed position input, missing shape assets, hash mismatch and animation-only failure preserve current area assessment, counts and coverage. Static fallback and keyboard selection remain usable.
- Switching 2D/3D changes no API query or result. Shape/model requests stay same-origin, satisfy CSP and use immutable manifest revisions. Measure selection cost, response bytes, rendering cost and memory alongside ADR 0011's desktop/mobile checks.

References: [GTFS trips and shapes](https://gtfs.org/documentation/schedule/reference/#shapestxt), [GTFS-Realtime trip descriptors](https://gtfs.org/documentation/realtime/reference/#message-tripdescriptor), [accepted capture/event semantics](capture-event-contract.md).

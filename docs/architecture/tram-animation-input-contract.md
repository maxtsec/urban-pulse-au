# MAP-02 tram animation input contract

Date: 6 October 2026. Status: **Proposed for architect review**. [ADR 0011](../adr/0011-southbank-building-massing.md) accepts the rendering stack, truth classes and 30-second display delay. This document proposes the missing transport metadata, playback protocol, API placement and bounds. Merging this proposal does not accept those decisions or authorize their implementation. Progress remains in the [delivery plan](../delivery-plan.md).

## Decisions and implementation prerequisites

The current `VehiclePosition` has only `vehicle_id`, `route_id`, `position` and `observed_at`. Neither the event contract nor retained fixture supplies trip identity or a verified shape link. The current frontend advances 15 scenario seconds after each two-second wait and fetches a snapshot; that produces discrete steps.

| Decision | Recommended proposal | Alternative and trade-off |
| --- | --- | --- |
| Transport metadata | Review an additive, nullable trip descriptor in the public transport event contract, then update normalization, retained history and the synthetic fixture together | A new event major version gives stricter mandatory metadata, but needs dual-reader/replay compatibility. Keeping the existing contract supports only static markers |
| Playback | A continuous logical playhead over a complete, bounded playback window, stopping at each data/state boundary | Keep discrete snapshot stepping, explicitly a static replay; it does not deliver MAP-02 moving trams |
| API placement | Keep A as the compatibility baseline pending payload acceptance; compare measured sizes below before choosing | B can avoid animation downloads in 2D, but needs an explicit amendment to ADR 0011's view-toggle request rule |

**MAP-02 prerequisites:** accept and implement the public transport-contract change (schema/version compatibility, validation and tests); retain original receipt evidence; author trip-complete synthetic observations; verify static GTFS trip-to-shape mapping and its manifest; accept this playback/API proposal and its bounds. These prerequisites apply to MAP-02 only. MAP-01 building massing can proceed independently after DEMO-01.

The transport proposal needs `trip_id`, service date/start time where required to identify a repeated trip instance, and nullable `direction_id`, alongside the existing route ID. Resolve `shape_id` from that trip in a pinned static GTFS release; do not invent a producer shape ID or guess from route alone. Matching output belongs to the Location Intelligence view model, not a new observed position or domain fact. Old events remain readable and render statically when linkage is missing. Live enablement and provider-field verification remain SRC-02 gates.

## API placement and size

| Option | Data path | Cost and compatibility |
| --- | --- | --- |
| A: additive `tram_animation` in the area snapshot | Return the bounded window with the existing area request | Atomic input alignment and ADR 0011's unchanged requests across 2D/3D; 2D also downloads and parses the animation payload |
| B: separate animation endpoint, requested only for animation | Request the same scenario/time as the area snapshot and verify scope/clock alignment | Avoids animation payloads in static 2D; adds request coordination, buffering and partial failures. Requires architect approval to amend ADR 0011's rule that view toggles do not change API requests |

The [payload estimate](../evidence/map-02-animation-payload.md) measures synthetic JSON for both ordinary and dense windows, including IDs, receipts and matching metadata. It is an encoding estimate, not a network or production benchmark. Both placements carry the same animation content when enabled; B adds alignment fields. No claim that the addition is small is justified before those sizes and the eventual fixture measurements are accepted.

The endpoint/query proposal must also define fractional scenario clocks for seek equivalence before implementation; the current API accepts integer seconds.

The tables below describe A. Under B, only the separate response adds `scope_id` and `clock_at`, which must equal the parent `composition.timeline_id` and `clock.at`. The proposed observation/byte limits and playback rules apply to both.

## Proposed wire fields

Receipt/observation timestamps are UTC RFC 3339. Trip service date/start time retain the GTFS service-calendar convention and source timezone; they are not UTC receipt timestamps. Coordinates are finite WGS84 longitude/latitude; distances are metres. Under A, inherit scope, start clock, vehicle limit/order and truncation from the parent. Do not repeat `scope_id`, `clock_at`, `max_vehicles` or `vehicles_truncated`. The existing area `policy_version` remains separate from the animation policy.

| `tram_animation` field | Meaning |
| --- | --- |
| `contract_version` | `tram-animation-input-v1` |
| `display_policy_version` | `tram-display-delay-v1`; display time is derived from the playhead minus 30 seconds |
| `status`, `reason` | `ready` or `unavailable`, with a nullable diagnostic code; an animation failure preserves the valid city view |
| `window_end` | Exclusive upper bound for this response's complete playback window; start is parent `clock.at` |
| `position_input` | `{state, received_at, capture_ids}`; `available`, `unknown` or `error`, derived from the position input independently of service-alert coverage |
| `shapes` | Null or `{revision, sha256, url}` for an immutable same-origin manifest and referenced geometry |
| `vehicles` | One entry per parent vehicle when ready; empty when unavailable. Each entry has `vehicle_id`, `source`, `latest_observation: {source, event_id}`, nullable `startup_observation` with the same reference format, and `observations` |

Each observation contains:

| Field | Meaning |
| --- | --- |
| `source`, `event_id`, `revision` | Original accepted event identity/revision; `(source, event_id)` identifies the sample |
| `capture_ids` | Original unique capture references, unchanged by redelivery |
| `observed_at` | Provider observation time, nullable; missing time disables interpolation |
| `received_at` | First successful application receipt. Fixtures use `started_at + at_seconds` of the first accepted frame; live support requires retained original receipt evidence. Never request, replay or retry time |
| `longitude`, `latitude` | Original observed coordinates |
| `shape_match` | `{status, trip_id, service_date, start_time, route_id, direction_id, shape_id, segment_id, continuity_id, distance_m}`. Status is `matched`, `unmatched` or `ambiguous`; unavailable values are null |

A matched sample identifies an unambiguous trip instance and directed shape component from `shapes.revision`. Nullable GTFS fields stay null; an absent value cannot bridge an ambiguous trip instance. The [source register](../source-register.md#tram-track-geometry-map-02) owns release, linkage and matching-tolerance verification.

The manifest records source ZIP/release and fixture hashes, coordinate/distance conventions, matching algorithm/version and accepted tolerance, and included/excluded IDs/counts. Each shape has contiguous components keyed by `segment_id`, with ordered vertices and increasing cumulative metre distances from the original shape origin. Preserve offsets when clipping; never join excluded spans. `continuity_id` identifies an accepted trajectory segment, breaking on trip/direction/shape/component changes, missing time/match, non-increasing observation times or decreasing distances. Derive it from the segment's first accepted event and linkage, so later receipts cannot rename an earlier segment. Illustrative fixture tracks are not verified matching evidence.

## Continuous clock and complete windows

Let **a** be the parent snapshot's clock. The backend supplies a complete interval **[a, b)**, at most 15 scenario seconds. Choose **b** as the earliest of the next 15-second grid boundary, scenario end, or any boundary where API-visible state can change: original input receipt, authored outage, warning/service validity, freshness expiry, membership or vehicle selection. Shorten it further if required by the sample/byte bounds below. Fixtures can determine these boundaries from retained history; do not assume a live feed's next arrival is known.

All returned observations have `received_at <= a`. Include enough accepted history to evaluate every display time in **[a - 30 s, b - 30 s)**. No future receipt is prefetched into this response. The parent facts, current-position list and membership remain valid until b; relative ages use the playhead, and any freshness category change is a boundary. Selecting all relevant context boundaries is part of the API implementation, not a client-side assessment engine. If that completeness cannot be established, return animation unavailable; do not advertise a window that crosses an unknown change.

Playback uses a monotonic elapsed timer only to advance the explicit logical playhead:

`p = a + elapsed_seconds * playback_rate`, with proposed `playback_rate = 7.5` (15 scenario seconds per two elapsed seconds).

At each browser animation frame, render the pure function `frame(p, window)` at **d = p - 30 s**. Meshes never integrate velocity or read wall time directly. This clarifies ADR 0011's scenario-clock rule: elapsed time schedules the scenario playhead; it is not another source of position data. A different frame rate changes which intermediate frames are sampled, not the pose at a given p.

Stop before committing a frame at b, fetch its new snapshot/window and resume only after validation. Show buffering and hold the last valid frame during delay/failure. Pause freezes p; resume anchors a new elapsed timer at that same p. Seek/scenario change cancels obsolete responses, requests the target clock and resets the timer. Direct seek and playback must produce the same tram pose, truth label and visible city state at p even if their request start times differ. Reaching the scenario end renders its final snapshot statically. Hidden-tab resume must not jump across unverified boundaries.

## Selection, discontinuities and delayed delivery

1. Reconstruct the accepted receipt prefix at a using the existing revision guard. Only original **APPLY** outcomes enter animation history. Duplicate/conflict/rejected/**SUPERSEDED** attempts add no sample. An earlier APPLY remains history after a later accepted revision; that is different from an incoming old revision rejected as SUPERSEDED.
2. A delayed observation becomes usable after receipt **only if its event is APPLY**. For example, revision 2 arriving after accepted revision 3 is excluded; revision 4 carrying an older observation time can apply but breaks continuity. This proposal does not introduce out-of-order historical ingestion or change `compare_revision`.
3. Select history around the **display interval**, retaining relevant old and new trip segments. Include the last dated observation at/before its left edge, all observations inside it, the first dated observation at/after its right edge, and the latest accepted observation needed by the parent. Retain continuity markers and any static fallback required by missing timestamps. Deduplicate by `(source, event_id)` and use canonical accepted revision order. Do not select only the latest trip.
4. For each d, interpolate only between consecutive bracketing observations with the same verified `continuity_id`. Across a trip/shape/gap break, hold the last eligible observed position at/before d; switch to the new segment only when d reaches its first observation. Never substitute the latest trip's first sample for that hold.
5. ADR 0011's before-first-observation exception applies only to the vehicle's first-ever observation, named by `startup_observation`, not the start of each new trip. That static fallback, a missing-time fallback and unavailable matching are labelled **Observed**, with the actual timestamp or unknown time; the 30-second legend applies to **Interpolated** motion and states that observed fallbacks are exceptions. No interpolation or speed is claimed for a fallback.
6. Stale/expired rules use p and existing visibility semantics. Unknown/error position input stops motion; other domains do not gate it. A failed shape load/hash verification or animation validation uses the labelled static fallback and preserves the city assessment and accessible list.

Proposed hard limits: parent vehicle cap (currently 100), **8 observations per vehicle** and **256 KiB of uncompressed compact UTF-8 animation JSON** including metadata. An ordinary 30-second-cadence window often needs only 2-3 samples; dense history can need more. Never drop an interior sample or discontinuity to fit the cap: shorten b deterministically to the earliest point at which another required sample would exceed a bound. If even the requested instant cannot fit, return `unavailable` with `window_limit`. Report the actual b; the frontend never advances past it. Bound historical query/validation cost separately and measure it in MAP-02.

### Acceptance examples

| Case | Expected frame |
| --- | --- |
| Observations at 0 and 30, received then; playhead 45 to just before 60 | Display 15 to just before 30, moving smoothly along the same verified shape; receipt 60 is unavailable until the next window |
| Trip X observation 30, trip Y observation 60; p=75, d=45 | Hold X at observation 30; never draw Y's position 60 under the delayed interpolation label. At p=90/d=60, Y may become the displayed segment |
| First-ever observation 0; p=15/d=-15 | Static Observed fallback at 0, with its timestamp; no interpolation claim |
| Revision 2 arrives after revision 3 | SUPERSEDED: never an animation sample, even after its receipt |
| Window [45,60), dense observations between display times 15 and 30 | Include all required interior samples/breaks, or end the window sooner; a three-sample shortcut cannot silently change the path |

MAP-02 tests must cover fractional playheads at different frame rates, pause/resume, direct seek/reload/rewind, slow/failed requests, hidden tabs, stale responses after seek, exact receipt/expiry boundaries, trip changes, missing timestamps, clipped gaps, sample/byte overflow and scenario end. Compare arbitrary p inside the window against a fresh snapshot at p (the fixture API will need fractional-clock support or an equivalent reviewed query contract). That public query change is also a prerequisite; rounding p to the existing integer `seconds` API is not an equivalence proof. Verify 2D/3D payload behaviour according to the chosen placement and measure payload, query, parsing, rendering and memory costs. These are implementation acceptance cases, not tests claimed to have run in this documentation PR.

References: [GTFS trips and shapes](https://gtfs.org/documentation/schedule/reference/#shapestxt), [GTFS-Realtime trip descriptors](https://gtfs.org/documentation/realtime/reference/#message-tripdescriptor), [capture/event semantics](capture-event-contract.md).

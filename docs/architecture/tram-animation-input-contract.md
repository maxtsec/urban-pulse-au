# MAP-02 tram animation input contract

Date: 7 October 2026. Status: **Accepted by the project architect on 2026-10-07**, subject to the explicit 2D playback decision below. Option B, separate parent validity, integer-millisecond clocks, compatible trip metadata, limits and truth labels define the MAP-02 implementation contract. [ADR 0011](../adr/0011-southbank-building-massing.md) records the corresponding amendments. This document does not claim runtime implementation; progress remains in the [delivery plan](../delivery-plan.md).

## Decisions and implementation prerequisites

The current `VehiclePosition` has only `vehicle_id`, `route_id`, `position` and `observed_at`. Neither the event contract nor retained fixture supplies trip identity or a verified shape link. The current frontend advances 15 scenario seconds after each two-second wait and fetches a snapshot; that produces discrete steps.

| Decision | Accepted rule | Consequence |
| --- | --- | --- |
| Transport metadata | Add a nullable trip descriptor to the existing v1 event | Old events remain readable; absent metadata renders statically |
| API placement | B: separate same-origin animation endpoint, requested only for enabled 3D animation | Static 2D avoids animation history; every response must align with its parent |
| City validity | Parent `valid_until`, independently computable without requesting animation | Both views share the same city-state boundaries |
| Clock | Integer milliseconds; legacy integer `seconds` remains accepted | Seek and playback use the same canonical instant |
| Playback | Rate 7.5; server-owned city boundaries and shared position freshness | Freshness-only transitions do not cause requests |
| Encoding | Per-vehicle `segments` table; observations reference continuity identity | Repeated trip/shape metadata is stored once per continuity segment |

**Implementation prerequisites:** implement and test the compatible public transport-contract addition; preserve original receipt evidence; author trip-complete synthetic observations; verify static GTFS trip-to-shape linkage and its manifest, matching tolerance and model asset licence. Live enablement and provider-field verification remain SRC-02 gates. These prerequisites apply to MAP-02, not completed MAP-01.

The trip descriptor carries `trip_id`, service date/start time where required to identify a repeated trip instance, and nullable `direction_id`, alongside the existing route ID. Resolve `shape_id` through that trip in a pinned static GTFS release; do not invent a producer shape ID or guess from route alone. Matching output belongs to the Location Intelligence view model, not a new observed position or domain fact. Preserve the serialized shape and receipt fingerprint of old events when the new field is absent; adding a default null must not invalidate persisted receipts or make an old retry conflict.

## API placement and alignment

Use **B**, a separate animation response. A (embedding animation in every area snapshot) is rejected because static 2D would repeatedly download and parse unused history. [Encoding measurements](../evidence/map-02-animation-payload.md) compare the former repeated metadata with the segment table; they are synthetic estimates, not runtime performance acceptance.

Both endpoints accept the same area/scenario and canonical parent clock. The animation request additionally identifies the expected `scope_id` from `composition.timeline_id`. The response's `scope_id` and `clock_at` must equal that parent timeline and `clock.at`, after UTC normalization. An active-import change, unsupported contract, mismatch, timeout or failed response cannot be combined with another parent: discard it and use the labelled static parent view. It does not change area assessment or trigger an extra area fetch just to repair animation. Re-pair animation after the next normal area update. Cancel obsolete animation requests on seek, scenario change or disabling animation; reject late replies even if cancellation arrives too late.

`scope_id` is a timeline identity, not the import ID. Its current inputs are capture identity, scenario policy, boundary revision and `POLICY_VERSION`. Shape revision/hash and animation/display policy versions are checked separately. Never assume that an identical clock alone identifies identical inputs.

### Integer-millisecond query contract

- Add `milliseconds` to area and animation queries: a non-negative integer offset from scenario start, bounded by `MAX_SECONDS * 1000`. Preserve legacy non-negative integer `seconds`, bounded by `MAX_SECONDS`; normalize it by exact multiplication by 1000. Neither supplied means zero. Supplying both is HTTP 422, even when equal. Reject fractional, negative, non-finite or out-of-range values; do not clamp or round user input.
- Use integer milliseconds for the logical playhead, window boundaries, seeks, pause/resume anchors and comparisons. Add `clock.milliseconds` to the parent; retain existing fields for old clients, deriving any whole-second display field by floor division. `clock.at` represents the exact canonical instant, never a rounded whole second. Animation `clock_at` represents the same instant.
- The scheduler converts monotonic elapsed time to integer microsecond ticks at its boundary, then uses integer arithmetic: `p_ms = anchor_ms + (elapsed_us * 15) // 2000`. This is rate 7.5, floored to the millisecond. Do not accumulate rounded frame deltas or float-valued scenario seconds; re-anchor at the exact paused playhead on resume.
- Preserve original receipt/observation timestamps and their precision. Evaluate a millisecond playhead against them without truncating an input into the past. A state transition between representable milliseconds takes effect at the first millisecond at/after it (ceiling), never before its timestamp. Boundary discovery and direct snapshot evaluation must agree on this rule.
- Integer scheduling makes an explicit `milliseconds=p_ms` seek comparable to playback at exactly p_ms. It does not promise that different frame rates sample the same intermediate frames.

### Parent snapshot additions

| Field | Meaning |
| --- | --- |
| `valid_until` | Exclusive UTC end of the parent city interval. Determined by the server from city boundaries and the 15-second grid, never animation sample/byte size |
| `clock.milliseconds` | Canonical integer offset matching `clock.at`; legacy seconds input remains compatible |
| `position_freshness_policy` | Shared version and thresholds, derived from the server constants described below |

Outside the scenario-end terminal snapshot, require `clock.at < valid_until`. At scenario end, `valid_until == clock.at` marks a terminal static snapshot; no further playback/window is advertised. If the server cannot establish city validity, fail the requested parent snapshot explicitly rather than inventing a validity interval. Unknown/error source coverage can still be valid city state within a known fixture interval. Future live support cannot assume a future feed receipt is knowable.

### Animation response

Receipt/observation timestamps are UTC RFC 3339. Trip service date/start time retain the GTFS service calendar and source timezone. Coordinates are finite WGS84 longitude/latitude; distances are metres. Retain the parent's capped vehicle order/selection and truncation; do not repeat `max_vehicles` or `vehicles_truncated`. The area `policy_version` remains separate from `display_policy_version`.

| Field | Meaning |
| --- | --- |
| `contract_version` | `tram-animation-input-v1` |
| `display_policy_version` | `tram-display-delay-v1`; display time is playhead minus 30,000 ms |
| `scope_id`, `clock_at` | Exact parent timeline and anchor clock; unchanged across animation-only subwindows |
| `status`, `reason` | `ready` or `unavailable`, nullable diagnostic code; unavailable retains the static parent view |
| `window_start`, `window_end` | Complete animation interval `[c,b)`, with `a <= c < b <= parent.valid_until` for ready responses; a is `clock_at`. End is shortened only by sample/byte bounds |
| `position_input` | `{state, received_at, capture_ids}`; `available`, `unknown` or `error`, independent of service-alert coverage |
| `shapes` | Null or `{revision, sha256, url}` for an immutable same-origin manifest and referenced geometry |
| `vehicles` | One entry per capped parent vehicle when ready; empty when unavailable. Each entry has `vehicle_id`, `source`, `latest_observation: {source, event_id}`, nullable `startup_observation`, `segments` and `observations` |

An initial request uses `window_start == clock_at`. To fetch a continuation without changing the area request, keep its `milliseconds`/`scope_id` anchored to the same parent and supply integer `window_start_milliseconds=c_ms` at the preceding animation end. Validate `a_ms <= c_ms < valid_until_ms`. This field is animation-only; `clock_at` remains a, not c. Returned start must equal the requested start. Reject an invalid continuation with HTTP 422 and an incompatible parent scope with HTTP 409. Never follow an animation response that crosses parent validity. For unavailable or terminal responses use null window bounds, an empty `vehicles` list and a reason; no playable interval is claimed.

### Startup reference

The accepted startup exception refers to the first APPLY observation for `(source, vehicle_id)` in the pinned replay scope's complete retained history, not the first sample of a trip, a window or a browser session. This does not claim the vehicle's first observation outside that scope.

`startup_observation` is non-null **if and only if** that complete history establishes the first observation, it has a non-null `observed_at`, it was received by a, and some display time in `[c - 30 s, b - 30 s)` precedes it with no received dated observation at or before that display time. Here a is the parent anchor, c is `window_start` and b is `window_end` (c=a for the initial window). Otherwise it is null: for example, once the whole display interval is at/after the first observation, when its time is unknown, or when complete history cannot establish the first record. Missing-time fallback follows the separate Observed rule below. If displaying the requested instant would require an unprovable startup exception, return animation `unavailable` with `startup_history_unknown` rather than guessing a first record.

A non-null reference must resolve to exactly one entry in the same vehicle's `observations`, with matching `(source, event_id)`; that entry counts toward the eight-sample and byte limits. Deduplicate it if it also serves as a bracket or latest observation. Include it during selection before checking limits; never silently omit it or substitute a new trip's first observation to make the payload fit. Use the startup fallback only while `d < startup.observed_at` and ordinary bracket/hold selection has no received dated observation at or before d. Reconstruct the reference from retained inputs on every seek, independently of browser visits.

### Observations

Each observation contains:

| Field | Meaning |
| --- | --- |
| `source`, `event_id`, `revision` | Original accepted event identity/revision; `(source, event_id)` identifies the sample |
| `capture_ids` | Original unique capture references, unchanged by redelivery |
| `observed_at` | Provider observation time, nullable; missing time disables interpolation |
| `received_at` | First successful application receipt. Fixtures use `started_at + at_seconds` of the first accepted frame; live support requires retained original receipt evidence. Never request, replay or retry time |
| `longitude`, `latitude` | Original observed coordinates |
| `shape_match` | `{status, continuity_id, distance_m}`. Status is `matched`, `unmatched` or `ambiguous`; unmatched/ambiguous samples have null reference/distance |

Each vehicle's `segments` is an object keyed by `continuity_id`. Each value stores `{trip_id, service_date, start_time, route_id, direction_id, shape_id, segment_id}` once. `segment_id` names a clipped geometry component; the table key names a trajectory continuity segment, and the two are not interchangeable. Include only entries referenced by returned observations. Every matched observation resolves exactly one key in its own vehicle table and has a finite non-negative `distance_m` within that component. Dangling/cross-vehicle references, duplicate JSON keys or invalid linkage invalidate animation; never infer a missing entry. Unmatched/ambiguous observations remain in history as continuity breaks and observed fallbacks, with their original event references available for evidence.

A matched sample identifies an unambiguous trip instance and directed shape component from `shapes.revision`. Nullable GTFS fields stay null; an absent value cannot bridge an ambiguous trip instance. The [source register](../source-register.md#tram-track-geometry-map-02) owns release, linkage and matching-tolerance verification.

The manifest records source ZIP/release and fixture hashes, coordinate/distance conventions, matching algorithm/version and accepted tolerance, and included/excluded IDs/counts. Each shape has contiguous components keyed by `segment_id`, with ordered vertices and increasing cumulative metre distances from the original shape origin. Preserve offsets when clipping; never join excluded spans. `continuity_id` identifies an accepted trajectory segment, breaking on trip/direction/shape/component changes, missing time/match, non-increasing observation times or decreasing distances. Derive it from the segment's first accepted event and linkage, so later receipts cannot rename an earlier segment. Illustrative fixture tracks are not verified matching evidence.

## Continuous clock and complete windows

Let **a** be the parent clock and **v** its `valid_until`. Independently of animation, the server chooses v as the earliest boundary strictly after a among the next 15-second scenario grid boundary, scenario end, original input receipt, authored outage, warning/service validity, domain-coverage expiry, membership or vehicle selection change. Apply transitions exactly at a before returning the new snapshot. Position age/freshness transitions alone do not end this interval: the client uses the shared policy below. Both 2D and 3D can discover v using only the parent endpoint.

For a ready animation request starting at **c** (initially a), begin with **b = v**; shorten b only as required by the eight-sample or byte limits. Never shorten parent v for animation size. All observations in every continuation have `received_at <= a`. Select enough accepted history to evaluate every display time in `[c - 30 s, b - 30 s)` without crossing a receipt boundary or omitting a discontinuity. No future receipt is prefetched.

The parent domain facts, latest observed coordinates and membership remain valid on `[a,v)`. Position freshness/visibility are evaluated at the playhead; parent values describe a. A required animation limit that cannot fit even the requested instant yields `unavailable/window_limit`; it does not shrink city validity. A client with a valid ready animation advances only below `min(valid_until, window_end)`; static 2D or animation fallback uses valid_until alone.

At b<v, request only the next animation subwindow, paired with the same parent; buffer at the boundary until it arrives, or explicitly enter labelled static fallback. At v, both views request the new parent first, then 3D may request its paired animation. Switching views cannot change those logical area-request boundaries or parameters. Network buffering can change elapsed wall-clock timing, not the requested city instants. Validate monotonic progress: an empty/non-advancing ready window is invalid, not a reason to spin requests.

### Position freshness within a window

The accepted **parent snapshot** field, shared by 2D and 3D, is `position_freshness_policy: {version, stale_after_seconds, expired_after_seconds}`. The 120/300-second fixture thresholds are already accepted, but **`southbank-position-freshness-v1` is the newly accepted wire version name, still to be implemented**. In the future serializer, derive `stale_after_seconds` and `expired_after_seconds` directly from `POSITION_STALE_SECONDS` and `POSITION_EXPIRED_SECONDS` in `urbanpulse.location.city`, the same constants used by `position_freshness` and the server's checkpoint scheduling. Review/version any threshold change and keep serialization, server evaluation and checkpoint timing consistent; do not maintain independent frontend or serializer constants. This adds a versioned public view contract without approving a live TTL.

At playhead p, apply the policy to each vehicle's **latest accepted observation** named by the parent, never an older sample chosen for the delayed pose. Null or future `observed_at` means `unknown`; otherwise compare elapsed integer microseconds against the supplied second thresholds multiplied by 1,000,000 (without truncating observation timestamps): `expired` at/after the expiry threshold, `stale` at/after the stale threshold, and `current` otherwise. Expired vehicles are hidden on the map; the last-known list remains. Stale vehicles are static and dimmed. Both views use the same evaluator for labels, map visibility and any visible-marker tally. Preserve the server's area assessment, source coverage, membership, `positions_total`, cap and truncation: those do not depend on this position-age display calculation.

Validate a supported policy version and finite ordered thresholds (`0 <= stale < expired`). Missing/invalid/unsupported policy prevents continuous playback; retain the static server snapshot with an explicit unavailable reason rather than guessing values. Verify browser/server parity at each threshold and immediately before/after it, including null/future timestamps. With 100 staggered vehicle age transitions and no domain/input changes, the parent 15-second interval must remain intact and trigger **zero freshness-only requests**. Other data boundaries may still shorten it; measure those requests and buffering in MAP-02.

### Playhead scheduling

The scheduler above advances an explicit millisecond playhead at rate 7.5. Render `frame(p_ms, window)` at `d_ms = p_ms - 30000`. Meshes never integrate velocity or read wall time independently. Elapsed time schedules the logical clock; it is not another source of position data.

Stop before committing a frame at the effective boundary. Show buffering and hold the last valid frame during a request; a failed animation request may explicitly switch to labelled static fallback with the valid parent. Never advance city state beyond valid_until while its next parent is missing. Pause freezes p_ms; resume anchors the timer there. Seek/scenario change cancels obsolete replies, requests the exact target milliseconds and resets the timer. Direct seek and playback must produce the same pose, truth label and visible city state at p_ms, independent of request start time and sample chunking. At scenario end render the final snapshot statically. Hidden-tab resume must not jump across unverified boundaries.

### 2D mode decision

**Awaiting the architect's choice:** recommend the same continuous millisecond playhead and parent validity protocol for 2D, with observed-position markers held until a new accepted observation, no animation request and no 1.5-second glide. The alternative is retaining the 15-second stepped 2D exception with separately specified state-boundary handling. This choice must be resolved in this documentation PR before implementation; it is not inferred from choosing endpoint B.

## Selection, discontinuities and delayed delivery

1. Reconstruct the accepted receipt prefix at a using the existing revision guard. Only original **APPLY** outcomes enter animation history. Duplicate/conflict/rejected/**SUPERSEDED** attempts add no sample. An earlier APPLY remains history after a later accepted revision; that is different from an incoming old revision rejected as SUPERSEDED.
2. A delayed observation becomes usable after receipt **only if its event is APPLY**. For example, revision 2 arriving after accepted revision 3 is excluded; revision 4 carrying an older observation time can apply but breaks continuity. This contract does not introduce out-of-order historical ingestion or change `compare_revision`.
3. Select history around the **display interval**, retaining relevant old and new trip segments. Include the last dated observation at/before its left edge, all observations inside it, the first dated observation at/after its right edge, and the latest accepted observation needed by the parent. Retain continuity markers and any static fallback required by missing timestamps. Deduplicate by `(source, event_id)` and use canonical accepted revision order. Do not select only the latest trip.
4. For each d, interpolate only between consecutive bracketing observations with the same verified `continuity_id`. Across a trip/shape/gap break, hold the last eligible observed position at/before d; switch to the new segment only when d reaches its first observation. Never substitute the latest trip's first sample for that hold.
5. Use ADR 0011's amended startup exception only for the scope's first observation as defined by `startup_observation`, with the truth labels below.
6. Stale/expired rules use p and the server-supplied position-freshness policy above. Unknown/error position input stops motion; other domains do not gate it. A failed shape load/hash verification or animation validation uses the labelled static fallback and preserves the city assessment and accessible list.

### Truth labels

Labels describe provenance, not whether an object happens to be moving. The legend must say: "Interpolated positions: 30-second display delay. Observed holds/fallbacks: recorded position and timestamp."

| Rendered case | Label and displayed time |
| --- | --- |
| Within a valid same-segment bracket, **including either observation endpoint** | **Interpolated**, display time d and both supporting observation times; retain this class when paused, buffering or the two positions coincide |
| An isolated observation with no valid bracket, rendered statically | **Observed**, that observation's actual timestamp and hold/fallback reason |
| Holding the old trip's last position across a trip/shape break | **Observed**, the held observation's timestamp; never the next trip's timestamp |
| Holding the latest received position because d is later than it | **Observed**, that latest observation's timestamp; no extrapolation claim |
| Startup, missing-time, unmatched-shape or stale/error static fallback at an observation | **Observed**, the selected observation's timestamp or "observation time unknown"; explain the fallback reason |

Keep **Interpolated** throughout a supported continuous trajectory, including exact observation times. At a shared endpoint, prefer the following valid bracket when available, otherwise the preceding valid bracket; both use the same label and endpoint coordinate. Use **Observed** only for an observed-position hold or fallback, not for a single frame merely because d equals a sample time. This classification depends on the valid bracket at d, not the previous rendered frame or browser frame rate.

Freezing an interpolated frame during a network wait does not relabel it Observed; the playhead and its existing label remain frozen. Expired/hidden positions retain their observation metadata in the accessible list. At p=75/d=45 with X observed at 30 and Y at 60, the held X position is Observed at 30; at p=90/d=60, Y is Observed at 60 if it still has no valid same-trip bracket; with a received second Y sample forming a valid bracket, it is Interpolated even at that endpoint. Interpolation resumes only with a valid bracket within Y.

Accepted hard limits: parent vehicle cap (currently 100), **8 observations per vehicle** and **256 KiB of uncompressed compact UTF-8 animation JSON**, including the full response, alignment fields, segment tables and metadata. An ordinary 30-second-cadence window often needs only 2-3 samples; dense history can need more. Never drop an interior sample or discontinuity to fit the cap: shorten b deterministically to the earliest point at which another required sample would exceed a bound. If even the requested instant cannot fit, return `unavailable` with `window_limit`. Report the actual b; the frontend never advances past it. Bound historical query/validation cost separately and measure it in MAP-02.

### Acceptance examples

| Case | Expected frame |
| --- | --- |
| Parent anchor 45,000 ms, valid until 60,000 ms; animation ends at 52,000 ms | Request animation continuation with `milliseconds=45000` and `window_start_milliseconds=52000`; retain parent and its clock, with no area request |
| New city input received at 52,750 ms | Parent validity ends at 52,750 ms in both views, independently of animation bounds; evaluate the new input at that exact millisecond |
| Both `seconds=45` and `milliseconds=45000` supplied | HTTP 422 despite equivalent values; a single `milliseconds=45751` selects exactly 45.751 scenario seconds |
| Observations at 0 and 30, received then; playhead 45 to just before 60 | Display 15 to just before 30, moving smoothly along the same verified shape; receipt 60 is unavailable until the next window |
| Trip X observation 30, trip Y observation 60; p=75, d=45 | Hold X as **Observed at 30**; never draw Y's position 60 under the delayed interpolation label. At p=90/d=60, Y may become the displayed segment |
| Three received same-segment observations at 0, 30 and 60; p=60/d=30 | **Interpolated** at the middle observation, just as immediately before/after it; no one-frame Observed flash |
| First observation in the complete replay scope at 0; p=15/d=-15 | Static Observed fallback at 0, with its timestamp; no interpolation claim |
| Revision 2 arrives after revision 3 | SUPERSEDED: never an animation sample, even after its receipt |
| Window [45,60), dense observations between display times 15 and 30 | Include all required interior samples/breaks, or end the window sooner; a three-sample shortcut cannot silently change the path |

MAP-02 tests must cover startup references (null cases, same-vehicle resolution, deduplication, limits and incomplete history), truth labels for both hold cases and inclusive bracket endpoints at different frame rates, serializer/server/checkpoint threshold consistency, client/server freshness parity and staggered expiry without extra requests, plus fractional playheads at different frame rates, pause/resume, direct seek/reload/rewind, slow/failed requests, hidden tabs, stale responses after seek, exact receipt/expiry boundaries, trip changes, missing timestamps, clipped gaps, sample/byte overflow and scenario end. Compare arbitrary integer p_ms inside a window against a fresh `milliseconds=p_ms` snapshot; integer-second rounding is not an equivalence proof. Test mutually exclusive time parameters, sub-millisecond input boundaries, millisecond threshold edges, pause/resume at the same integer tick, chunk changes and active-import mismatch. Verify 2D never calls animation, 3D continuation requests do not cause extra area requests, animation size never changes valid_until, and terminal/invalid windows never loop. Verify 2D/3D payload behaviour under B and measure payload, query, parsing, rendering and memory costs. These are implementation acceptance cases, not tests claimed to have run in this documentation PR.

References: [GTFS trips and shapes](https://gtfs.org/documentation/schedule/reference/#shapestxt), [GTFS-Realtime trip descriptors](https://gtfs.org/documentation/realtime/reference/#message-tripdescriptor), [capture/event semantics](capture-event-contract.md).

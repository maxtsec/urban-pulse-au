# MAP-02 tram animation input contract

Date: 7 October 2026. Status: **Accepted by the project architect on 2026-10-07**. Both views use the continuous playhead; vehicle-local failures use independent static fallbacks. Option B, separate parent validity, integer-millisecond clocks, compatible trip metadata, limits and truth labels define the MAP-02 implementation contract. [ADR 0011](../adr/0011-southbank-building-massing.md) records the corresponding amendments. This document does not claim runtime implementation; progress remains in the [delivery plan](../delivery-plan.md).

## Decisions and implementation prerequisites

The current `VehiclePosition` has only `vehicle_id`, `route_id`, `position` and `observed_at`. Neither the event contract nor retained fixture supplies trip identity or a verified shape link. The current frontend advances 15 scenario seconds after each two-second wait and fetches a snapshot; that produces discrete steps.

| Decision | Accepted rule | Consequence |
| --- | --- | --- |
| Transport metadata | Add a nullable trip descriptor to the existing v1 event | Old events remain readable; absent metadata renders statically |
| API placement | B: separate same-origin animation endpoint, requested only for enabled 3D animation | Static 2D avoids animation history; every response must align with its parent |
| City validity | Parent `valid_until`, independently computable without requesting animation | Both views share the same city-state boundaries |
| Clock | Integer milliseconds; legacy integer `seconds` remains accepted | Seek and playback use the same canonical instant |
| Playback | Both views use a continuous millisecond playhead at rate 7.5; server-owned city boundaries and shared position freshness | 2D has static observed markers, no glide and no animation requests |
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

### Required clock migration

This is an implementation prerequisite, not a claim about current runtime support. `application.composition.transition_clocks` and `application.city_checkpoints.clocks()` currently round transitions up to whole seconds. Replace both with a shared integer-millisecond boundary calculation covering receipts, validity, coverage, selection and freshness checkpoints. Use integer `timedelta` components, not float `total_seconds()` followed by second rounding. For an offset `u` in integer microseconds, the first representable boundary is `-(-u // 1000)`. A warning effective at 52.4 s must produce 52,400 ms, not 53,000 ms; a 52,500 ms direct seek and playback must agree.

Carry milliseconds through composition, checkpoint scheduling/identity and replay evaluation without converting back to whole seconds. Preserve compatibility for existing second-based run/checkpoint records through explicit unit/version handling; do not reinterpret persisted seconds as milliseconds. Test this migration before enabling the new endpoint.

Evidence queries also accept mutually exclusive `milliseconds`/legacy `seconds`. Every `evidence_url` generated for the new parent uses its exact `milliseconds`, with the same scenario and retained scope/import alignment. Evidence at 52,999 ms includes an input received at 52,750 ms; it must not link to `seconds=52`. Mismatched or unavailable retained scope fails explicitly instead of displaying another import's evidence.

### Parent snapshot additions

| Field | Meaning |
| --- | --- |
| `valid_until` | Exclusive UTC end of a nonterminal parent city interval; null only at scenario end. Determined by server city boundaries and the 15-second grid, never animation size |
| `terminal` | True exactly at `MAX_SECONDS * 1000`; false at every earlier clock |
| `clock.milliseconds` | Canonical integer offset matching `clock.at`; legacy seconds input remains compatible |
| `position_freshness_policy` | Shared version and thresholds, derived from the server constants described below |

For `terminal=false`, require a non-null `valid_until` strictly after `clock.at`. At scenario end return `terminal=true, valid_until=null` after applying transitions at that exact instant. Render the final parent statically; do not search for a subsequent boundary, compare null as a timestamp or request another animation window. If the server cannot establish city validity, fail the requested parent snapshot explicitly rather than inventing a validity interval. Unknown/error source coverage can still be valid city state within a known fixture interval. Future live support cannot assume a future feed receipt is knowable.

### Animation response

Receipt/observation timestamps are UTC RFC 3339. Trip service date/start time retain the GTFS service calendar and source timezone. Coordinates are finite WGS84 longitude/latitude; distances are metres. Retain the parent's capped vehicle order/selection and truncation; do not repeat `max_vehicles` or `vehicles_truncated`. The area `policy_version` remains separate from `display_policy_version`.

| Field | Meaning |
| --- | --- |
| `contract_version` | `tram-animation-input-v1` |
| `display_policy_version` | `tram-display-delay-v1`; display time is playhead minus 30,000 ms |
| `scope_id`, `clock_at` | Exact parent timeline and anchor clock; unchanged across animation-only subwindows |
| `status`, `reason` | `ready` when the aligned response can be evaluated (including mixed/all-static vehicles); `unavailable` only for a response-wide failure or terminal parent, with a diagnostic code |
| `window_start`, `window_end` | Complete animation interval `[c,b)`, with `a <= c < b <= parent.valid_until` for ready responses; a is `clock_at`. End is shortened only by sample/byte bounds |
| `position_input` | `{state, received_at, capture_ids}`; `available`, `unknown` or `error`, independent of service-alert coverage |
| `shapes` | Null or `{revision, sha256, url}` for an immutable same-origin manifest and referenced geometry |
| `vehicles` | One entry per capped parent vehicle when response-ready. Every entry has `vehicle_id`, `source`, `status` (`ready` or `static`) and `reason` (null when ready; diagnostic code when static). Ready entries also have `latest_observation: {source, event_id}`, nullable `startup_observation`, `segments` and `observations`. Static entries omit those animation fields and use the paired parent observation. Empty on response-wide unavailability |

An initial request uses `window_start == clock_at`. To fetch a continuation without changing the area request, keep its `milliseconds`/`scope_id` anchored to the same parent and supply integer `window_start_milliseconds=c_ms` at the preceding animation end. Validate `a_ms <= c_ms < valid_until_ms`. This field is animation-only; `clock_at` remains a, not c. Returned start must equal the requested start. Reject an invalid continuation with HTTP 422 and an incompatible parent scope with HTTP 409. Never follow an animation response that crosses parent validity. Check `parent.terminal` before interval validation. For unavailable or terminal responses use null window bounds, an empty `vehicles` list and a reason (`terminal` at scenario end); no playable interval is claimed. Per-vehicle static fallback does not null the shared bounds or stop healthy vehicles; an all-static ready response can cover the remaining parent interval without animation-only polling.

### Startup reference

The accepted startup exception refers to the first APPLY observation for `(source, vehicle_id)` in the pinned replay scope's complete retained history, not the first sample of a trip, a window or a browser session. This does not claim the vehicle's first observation outside that scope.

`startup_observation` is non-null **if and only if** that complete history establishes the first observation, it has a non-null `observed_at`, it was received by a, and some display time in `[c - 30 s, b - 30 s)` precedes it with no received dated observation at or before that display time. Here a is the parent anchor, c is `window_start` and b is `window_end` (c=a for the initial window). Otherwise it is null: for example, once the whole display interval is at/after the first observation, when its time is unknown, or when complete history cannot establish the first record. Missing-time fallback follows the separate Observed rule below. If displaying the requested instant would require an unprovable startup exception, mark only that vehicle `static/startup_history_unknown`, using its parent observation, rather than guessing a first record. Other vehicles keep their animation.

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
| `trip` | Omitted for matched samples (resolved from `segments`); mandatory inline object for unmatched/ambiguous samples: `{trip_id, service_date, start_time, route_id, direction_id}`. Preserve known producer fields and use null for missing values |

Each vehicle's `segments` is an object keyed by `continuity_id`. Each value stores `{trip_id, service_date, start_time, route_id, direction_id, shape_id, segment_id}` once. `segment_id` names a clipped geometry component; the table key names a trajectory continuity segment, and the two are not interchangeable. Include only entries referenced by returned observations. Every matched observation resolves exactly one key in its own vehicle table and has a finite non-negative `distance_m` within that component. Invalid linkage or dangling/cross-vehicle references cause that vehicle to use `static/invalid_linkage`; never infer a missing entry. An unparseable envelope or duplicate JSON keys invalidate the response because its identity cannot be trusted. Unmatched/ambiguous observations remain in history as continuity breaks and observed fallbacks, with inline trip/route metadata as well as their original event references. Inline trip identity does not make an unmatched sample interpolatable: keep its continuity break, never bridge an ambiguous instance, and distinguish an old-trip hold from an unmatched fallback.

A matched sample identifies an unambiguous trip instance and directed shape component from `shapes.revision`. Nullable GTFS fields stay null; an absent value cannot bridge an ambiguous trip instance. The [source register](../source-register.md#tram-track-geometry-map-02) owns release, linkage and matching-tolerance verification.

The manifest records source ZIP/release and fixture hashes, coordinate/distance conventions, matching algorithm/version and accepted tolerance, and included/excluded IDs/counts. Each shape has contiguous components keyed by `segment_id`, with ordered vertices and increasing cumulative metre distances from the original shape origin. Preserve offsets when clipping; never join excluded spans. `continuity_id` identifies an accepted trajectory segment, breaking on trip/direction/shape/component changes, missing time/match, non-increasing observation times or decreasing distances. Derive it from the segment's first accepted event and linkage, so later receipts cannot rename an earlier segment. Illustrative fixture tracks are not verified matching evidence.

## Continuous clock and complete windows

For a nonterminal parent only, let **a** be its clock and **v** its non-null `valid_until`. Terminal parents use the separate rule above. Independently of animation, the server chooses v as the earliest boundary strictly after a among the next 15-second scenario grid boundary, scenario end, original input receipt, authored outage, warning/service validity, domain-coverage expiry, membership or vehicle selection change. Apply transitions exactly at a before returning the new snapshot. Position age/freshness transitions alone do not end this interval: the client uses the shared policy below. Both 2D and 3D can discover v using only the parent endpoint.

For a ready animation request starting at **c** (initially a), begin with **b = v**; shorten b only as required by the eight-sample or byte limits. Never shorten parent v for animation size. All observations in every continuation have `received_at <= a`. Select enough accepted history to evaluate every display time in `[c - 30 s, b - 30 s)` without crossing a receipt boundary or omitting a discontinuity. No future receipt is prefetched.

The parent domain facts, latest observed coordinates and membership remain valid on `[a,v)`. Position freshness/visibility are evaluated at the playhead; parent values describe a. A vehicle whose required history cannot fit at the requested instant uses its labelled static fallback under the allocation rule below; it does not shrink city validity or disable other vehicles. A client with a valid ready animation advances only below `min(valid_until, window_end)`; static 2D or animation fallback uses valid_until alone.

At b<v, request only the next animation subwindow, paired with the same parent; buffer at the boundary until it arrives, or explicitly enter labelled static fallback. At v, both views request the new parent first, then 3D may request its paired animation. Switching views cannot change those logical area-request boundaries or parameters. Network buffering can change elapsed wall-clock timing, not the requested city instants. Validate monotonic progress: an empty/non-advancing ready window is invalid, not a reason to spin requests.

### Position freshness within a window

The accepted **parent snapshot** field, shared by 2D and 3D, is `position_freshness_policy: {version, stale_after_seconds, expired_after_seconds}`. The 120/300-second fixture thresholds are already accepted, but **`southbank-position-freshness-v1` is the newly accepted wire version name, still to be implemented**. In the future serializer, derive `stale_after_seconds` and `expired_after_seconds` directly from `POSITION_STALE_SECONDS` and `POSITION_EXPIRED_SECONDS` in `urbanpulse.location.city`, the same constants used by `position_freshness` and the server's checkpoint scheduling. Review/version any threshold change and keep serialization, server evaluation and checkpoint timing consistent; do not maintain independent frontend or serializer constants. This adds a versioned public view contract without approving a live TTL.

At playhead p, apply the policy to each vehicle's **latest accepted observation** named by the parent, never an older sample chosen for the delayed pose. Null or future `observed_at` means `unknown`; otherwise compare elapsed integer microseconds against the supplied integer-second thresholds multiplied by 1,000,000: `expired` at/after the expiry threshold, `stale` at/after the stale threshold, and `current` otherwise. Expired vehicles are hidden on the map; the last-known list remains. Stale vehicles are static and dimmed. Both views use the same evaluator for labels, map visibility and any visible-marker tally. Preserve the server's area assessment, source coverage, membership, `positions_total`, cap and truncation: those do not depend on this position-age display calculation.

Preserve original timestamp precision. The browser must use a strict custom UTC RFC 3339 parser accepting zero to six fractional digits, padding the fraction to microseconds and returning integer microseconds (`BigInt`); `Date.parse` is not an authoritative parser for this calculation. The server uses integer datetime/timedelta components, not float seconds. Canonical view timestamps use `Z`; unsupported precision/invalid dates fail validation rather than silently rounding. Compare `p_ms * 1000` to parsed timestamps and integer thresholds. An observation at 0.0004 s is still current at p=120,000 ms and becomes stale at 120,001 ms. Preserve the original timestamp for evidence and use the same precise parser for receipt gating and interpolation brackets.

Validate a supported policy version and finite ordered integer thresholds (`0 <= stale < expired`). Missing/invalid/unsupported policy prevents continuous playback; retain the static server snapshot with an explicit unavailable reason rather than guessing values. Verify browser/server parity at each threshold and immediately before/after it, including null/future timestamps. With 100 staggered vehicle age transitions and no domain/input changes, the parent 15-second interval must remain intact and trigger **zero freshness-only requests**. Other data boundaries may still shorten it; measure those requests and buffering in MAP-02.

### Playhead scheduling

The scheduler above advances an explicit millisecond playhead at rate 7.5. Render `frame(p_ms, window)` at `d_ms = p_ms - 30000`. Meshes never integrate velocity or read wall time independently. Elapsed time schedules the logical clock; it is not another source of position data.

Stop before committing a frame at the effective boundary. Show buffering and hold the last valid frame during a request; a failed animation request may explicitly switch to labelled static fallback with the valid parent. Never advance city state beyond valid_until while its next parent is missing. Pause freezes p_ms; resume anchors the timer there. Seek/scenario change cancels obsolete replies, requests the exact target milliseconds and resets the timer. Direct seek and playback must produce the same pose, truth label and visible city state at p_ms, independent of request start time and sample chunking. At scenario end render the final snapshot statically. Hidden-tab resume must not jump across unverified boundaries.

### 2D playback

Both views use the same continuous millisecond playhead, city boundaries and area-request parameters. MAP-02 replaces the former 15-second stepped 2D clock and 1.5-second glide. 2D markers remain at the latest received observed coordinates until a new parent supplies an observation; freshness and visibility update from the shared policy at p. 2D never requests animation history. Clock text and progress describe the logical playhead, including fractional time when exposed; pausing/seek never snaps back to the parent anchor. A receipt at 52,750 ms refreshes the parent in both views, not at the next 60,000 ms grid point.

## Selection, discontinuities and delayed delivery

1. Reconstruct the accepted receipt prefix at a using the existing revision guard. Only original **APPLY** outcomes enter animation history. Duplicate/conflict/rejected/**SUPERSEDED** attempts add no sample. An earlier APPLY remains history after a later accepted revision; that is different from an incoming old revision rejected as SUPERSEDED.
2. A delayed observation becomes usable after receipt **only if its event is APPLY**. For example, revision 2 arriving after accepted revision 3 is excluded; revision 4 carrying an older observation time can apply but breaks continuity. This contract does not introduce out-of-order historical ingestion or change `compare_revision`.
3. Select history around the **display interval**, retaining relevant old and new trip segments. Include the last dated observation at/before its left edge, all observations inside it, the first dated observation at/after its right edge, and the latest accepted observation needed by the parent. Retain continuity markers and any static fallback required by missing timestamps. Deduplicate by `(source, event_id)` and use canonical accepted revision order. Do not select only the latest trip.
4. For each d, interpolate only between consecutive bracketing observations with the same verified `continuity_id`. Across a trip/shape/gap break, hold the last eligible observed position at/before d; switch to the new segment only when d reaches its first observation. Never substitute the latest trip's first sample for that hold.
5. Use ADR 0011's amended startup exception only for the scope's first observation as defined by `startup_observation`, with the truth labels below.
6. Stale/expired rules use p and the server-supplied position-freshness policy above. Unknown/error position input stops motion; other domains do not gate it. A failed shared shape load/hash verification or envelope validation uses response-wide labelled static fallback; vehicle-specific validation falls back only for that vehicle. Both preserve the city assessment and accessible list.

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

### Vehicle-local fallback and payload allocation

Accepted hard limits remain the parent cap (currently 100), **8 observations per ready vehicle** and **256 KiB of uncompressed compact UTF-8 response JSON**, including alignment, statuses, segment tables and metadata. A normal trip change can exceed the byte limit even with four samples per vehicle. Window shortening cannot solve overflow in the history already required at its start.

Separate response failures (scope mismatch, invalid envelope, unavailable shared geometry) from vehicle failures. A missing startup history, invalid vehicle linkage, sample limit or byte allocation failure returns only that vehicle as `static`, with `startup_history_unknown`, `invalid_linkage`, `sample_limit` or `byte_limit`. Use the paired parent's observed location/time and an **Observed** label/reason; never label it as delayed interpolation. Retain all capped vehicles through these small stubs; do not discard an interior sample from a vehicle still labelled ready.

Allocation must be deterministic for seek and playback, not first-come network order. Use the canonical city interval containing p (bounded by the same grid/input/state transitions as parent validity, independently of the requested anchor). Use only history received by that canonical interval's left boundary; no later receipt is eligible. For each vehicle determine the maximum complete byte/sample requirement of any minimum one-millisecond window within that interval, retaining inclusive brackets, breaks, latest and startup references. This admission requirement is independent of animation subwindow selection. Reserve the full response envelope (including the maximum encoded clock/bound lengths within the interval) plus static stubs for all parent vehicles; in canonical parent order admit each eligible vehicle's complete requirement if its incremental reservation fits, otherwise retain its stub and continue to later vehicles. The admitted set and reasons stay fixed within this city interval for direct seeks and continuations. Source changes at its end trigger fresh admission. Bound and measure this calculation during implementation.

For admitted vehicles, start b at parent validity and shorten it only when the combined complete histories for `[c,b)` exceed the byte/sample bounds. Do not change admission merely because a longer window needs more samples; first shorten the window. The reserved minimum-window histories guarantee a nonempty representable window; test this explicitly. Serialize and check the actual whole body, including static stubs. Only if even the all-static envelope cannot fit may the entire response use `unavailable/envelope_limit`. If all vehicles are static, return ready with b=v and no animation-only continuation. Report b faithfully and never change parent validity. This trades some vehicles' animation detail for bounded payloads while preserving the rest; record ready/static counts in acceptance evidence.

### Acceptance examples

| Case | Expected frame |
| --- | --- |
| Parent anchor 45,000 ms, valid until 60,000 ms; animation ends at 52,000 ms | Request animation continuation with `milliseconds=45000` and `window_start_milliseconds=52000`; retain parent and its clock, with no area request |
| New city input received at 52,750 ms | Parent validity ends at 52,750 ms in both views, independently of animation bounds; evaluate the new input at that exact millisecond |
| Both `seconds=45` and `milliseconds=45000` supplied | HTTP 422 despite equivalent values; a single `milliseconds=45751` selects exactly 45.751 scenario seconds |
| Warning effective at 52.4 s; seek/playback at 52,500 ms | Both show the warning; shared transition and checkpoint boundaries are 52,400 ms |
| Observation at 0.0004 s; freshness at 120,000/120,001 ms | Current then stale in server and browser using exact integer microseconds |
| One startup history missing, 99 valid vehicles | Only the affected vehicle is `static/startup_history_unknown` |
| 100 vehicles with four samples and a trip break exceed 256 KiB | Deterministic per-vehicle admission retains a bounded response with healthy admitted vehicles ready; repeat seek/continuation yields the same admission |
| Scenario end | Final transitions applied; `terminal=true`, `valid_until=null`; no next request |
| Observations at 0 and 30, received then; playhead 45 to just before 60 | Display 15 to just before 30, moving smoothly along the same verified shape; receipt 60 is unavailable until the next window |
| Trip X observation 30, trip Y observation 60; p=75, d=45 | Hold X as **Observed at 30**; never draw Y's position 60 under the delayed interpolation label. At p=90/d=60, Y may become the displayed segment |
| Three received same-segment observations at 0, 30 and 60; p=60/d=30 | **Interpolated** at the middle observation, just as immediately before/after it; no one-frame Observed flash |
| First observation in the complete replay scope at 0; p=15/d=-15 | Static Observed fallback at 0, with its timestamp; no interpolation claim |
| Revision 2 arrives after revision 3 | SUPERSEDED: never an animation sample, even after its receipt |
| Window [45,60), dense observations between display times 15 and 30 | Include all required interior samples/breaks, or end the window sooner; a three-sample shortcut cannot silently change the path |

MAP-02 tests must cover startup references (null cases, same-vehicle resolution, deduplication, limits and incomplete history), truth labels for both hold cases and inclusive bracket endpoints at different frame rates, serializer/server/checkpoint threshold consistency, client/server freshness parity and staggered expiry without extra requests, plus fractional playheads at different frame rates, pause/resume, direct seek/reload/rewind, slow/failed requests, hidden tabs, stale responses after seek, exact receipt/expiry boundaries, trip changes, missing timestamps, clipped gaps, sample/byte overflow and scenario end. Compare arbitrary integer p_ms inside a window against a fresh `milliseconds=p_ms` snapshot; integer-second rounding is not an equivalence proof. Test mutually exclusive time parameters, sub-millisecond input boundaries, millisecond threshold edges, pause/resume at the same integer tick, chunk changes and active-import mismatch. Verify 2D never calls animation, 3D continuation requests do not cause extra area requests, animation size never changes valid_until, and terminal/invalid windows never loop. Verify 2D/3D payload behaviour under B and measure payload, query, parsing, rendering and memory costs. Also cover exact-millisecond evidence links, persisted checkpoint unit compatibility, unmatched/ambiguous inline trip preservation, one-vehicle startup failure, all-static envelopes and deterministic byte admission at different seek anchors in the same city interval. These are implementation acceptance cases, not tests claimed to have run in this documentation PR.

References: [GTFS trips and shapes](https://gtfs.org/documentation/schedule/reference/#shapestxt), [GTFS-Realtime trip descriptors](https://gtfs.org/documentation/realtime/reference/#message-tripdescriptor), [capture/event semantics](capture-event-contract.md).

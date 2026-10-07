# MAP-02: deterministic two-observation path interpolation

The pure [frontend geometry core](../../apps/web/src/animation/tram-path.ts) implements the accepted [two-observation constant-speed rule](../architecture/tram-animation-input-contract.md#two-observation-constant-speed-interpolation). It evaluates an already matched, consecutive observation pair without reading the clock, fetching data or changing application state. The current map is not wired to it yet.

`TramPath` validates and copies one complete shape's ordered WGS84 coordinates and supplied cumulative metre distances when the asset is prepared. It rejects non-finite/out-of-range coordinates, unequal array lengths, nonzero distance origins, decreasing distances and inconsistent coincident vertices. Original vertices, direction and outside-area spans are retained. Frame lookup uses binary search over cumulative distances, including duplicate distances at coincident vertices; it does not rescan or revalidate the shape every frame. Prepare once and reuse the path.

`interpolateTramBracket` accepts two matched observations, their continuity/shape identities, original integer-microsecond observation timestamps (`observedAtUs`) and an integer-millisecond **display** time. Comparisons and the interpolation fraction use `displayAtMs * 1000` against the exact observations, with safe-integer checks on the conversion and duration. Supporting timestamps remain microseconds (`observationTimesUs`); callers must not truncate them to milliseconds. Within an inclusive, increasing-time bracket, it calculates the linear fraction of path distance and locates that distance on the polyline. Unequal vertex spacing and bends do not change speed within a bracket. Equal matched distances hold position; successive brackets may have different speeds. Coordinates inside each source edge are interpolated linearly from its endpoints, using the supplied distance index rather than recalculating a geodesic or matching observations in the browser.

The result retains both observation timestamps, display time and the `Interpolated` label, including exact endpoints and zero-speed brackets. Invalid/unsafe clocks, out-of-path distances, reversed distance progression, shape/continuity changes and out-of-bracket display times return no interpolation. There is no extrapolation, easing or prediction. Input-array and returned-coordinate mutations cannot alter the prepared path. Repeated evaluation at the same display millisecond is independent of prior frames, seeking, pause or rewind.

## Integration boundary

The caller must supply receipt-eligible observations with verified matching and continuity, select consecutive pairs and apply the display delay exactly once. This helper does not authorize an unreceived sample, compute trip linkage or choose matching tolerance. It also does not implement freshness, window validity, startup rules, `Observed` holds/fallbacks, shared-endpoint pair selection, request scheduling or the millisecond import/checkpoint migration. At a shared endpoint the future renderer must prefer the following valid bracket as the contract specifies; either pair produces the same coordinate and label.

Those responsibilities remain with the animation projection/window and renderer. A `null` result is a signal for their existing contract fallback rules, not permission to hide the vehicle or change the area result. Route chunk selection and serving remain independent of this geometry primitive. No live delay, source policy, public event schema or UI behavior changes here.

## Validation and reproduction

From `apps/web`, with the locked dependencies installed and the project's Node 24 runtime:

```bash
npm run test:unit
npm run lint
npm run format:check
npm run build
```

The unit command type-checks its own configuration and uses Node's built-in TypeScript test support; no new dependency is added. CI now runs it before the production build. Tests cover quarter/half/three-quarter travel around an unevenly spaced bend, inclusive labels, zero speed, speed changes, fractional-second clocks, frame-order independence, sub-millisecond and epoch-microsecond boundaries, unsafe clock conversions, invalid brackets, continuity changes, coincident vertices and mutation isolation. They also check every original vertex of all 208 retained Southbank shapes against the supplied distance index. These are geometry-core tests, not evidence of end-to-end animated playback or managed performance.

Validation: all 13 typed frontend unit tests and 16 Python workflow/build-guard tests passed. Web lint, formatting, production build and Ruff passed. The real Docker web-build smoke passed under `python -O`, including both complete build-stage inventories and static asset export. Application browser flows are unchanged; no new animation UI or end-to-end playback acceptance is claimed.

The exact new source file is admitted to the web Docker allowlist; unit fixtures/configuration and private files remain outside the image. Progress and the remaining animation/serving work stay in the [delivery plan](../delivery-plan.md).

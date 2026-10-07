# MAP-02: exact UTC timestamps and receipt boundaries

The shared [frontend time helpers](../../apps/web/src/animation/exact-time.ts) implement the accepted [timestamp-precision rule](../architecture/tram-animation-input-contract.md#position-freshness-within-a-window). They prepare exact values for later window/receipt evaluation and the [interpolation core](map-02-path-interpolation.md). Current map playback and server clocks are unchanged.

`parseUtcMicroseconds` accepts canonical UTC view timestamps with uppercase `T`/`Z` and zero to six fractional digits. It validates Gregorian dates, including century leap-year rules, and returns epoch microseconds as `BigInt`. Fractions are padded, never truncated; noncanonical offsets, leap seconds, invalid dates, trailing whitespace and unsupported precision return `null`. Supported years are 0001–9999, matching the backend datetime range. No `Date.parse` or floating-point epoch arithmetic is used. Keep the original timestamp string on its observation/capture for evidence; the helper does not rewrite it.

`millisecondsToMicroseconds` validates a safe integer millisecond clock, converts it to `BigInt`, then multiplies by 1000. `receiptEligible` compares the **receipt timestamp** to the response's anchor clock. Receipt time and observation time may differ; do not substitute one for the other or gate receipts using the delayed vehicle display clock. Missing receipt timestamps or invalid anchors cannot become eligible.

`firstRepresentableMillisecond` calculates the ceiling of an exact microsecond timestamp, including negative timestamps before the epoch. A receipt at 52.7504 seconds is excluded at 52,750 ms and included at 52,751 ms. An exact-millisecond receipt is included at that millisecond. The returned boundary must itself fit a safe integer. These helpers do not replace backend checkpoint discovery or make the current API accept fractional clocks.

The interpolation core deliberately accepts safe-number microseconds. `safeObservationMicroseconds` bridges from the parser only when the integer is exactly representable; otherwise it returns `null` for the caller's contract fallback. Do not coerce a parser result with unchecked `Number()` or serialize internal `BigInt` values into JSON. Parser calendar support does not imply every date fits the interpolation core's numeric range.

## Verification

From `apps/web` with locked dependencies installed:

```bash
npm run test:unit
npm run lint
npm run format:check
npm run build
```

Tests cover fractional precision, malformed timestamps, Gregorian date limits, 144 independent whole-second calendar checks across representative leap/century years, pre-epoch ceilings, safe-integer bounds and an exact parser → receipt gate → interpolation example. `Date` is used only as an independent whole-second calendar oracle in tests; sub-millisecond expectations are asserted as integer literals. The existing path tests remain in the same unit suite.

Validation: 21 typed frontend unit tests and 16 Python workflow/build-guard tests passed. Web lint/format/build and Ruff passed. Real Docker web-build smoke under `python -O` passed both complete inventories and static asset export; only the exact new source file was added to the Docker allowlist.

This is an implementation building block. Runtime freshness policy evaluation, comparison with the real server freshness function, v2 fixture/import/checkpoint migration, window selection, scheduler wiring and end-to-end seek/playback parity remain separate work under the accepted contract. No freshness threshold, display delay, wire schema, route packaging or live-source policy changes here. Progress remains in the [delivery plan](../delivery-plan.md).

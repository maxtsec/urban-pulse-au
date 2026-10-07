# MAP-02: exact UTC timestamps and receipt boundaries

The shared [frontend time helpers](../../apps/web/src/animation/exact-time.ts) implement the accepted [timestamp-precision rule](../architecture/tram-animation-input-contract.md#position-freshness-within-a-window). They prepare exact values for later window/receipt evaluation and the [interpolation core](map-02-path-interpolation.md). Current map playback and server clocks are unchanged.

`parseUtcMicroseconds` accepts canonical UTC view timestamps with uppercase `T`/`Z` and zero to six fractional digits. It validates Gregorian dates, including century leap-year rules, and returns epoch microseconds as `BigInt`. Fractions are padded, never truncated; noncanonical offsets, leap seconds, invalid dates, trailing whitespace and unsupported precision return `null`. Supported years are 0001–9999, matching the backend datetime range. No `Date.parse` or floating-point epoch arithmetic is used. Keep the original timestamp string on its observation/capture for evidence; the helper does not rewrite it.

`millisecondsToMicroseconds` validates a safe integer millisecond clock, converts it to `BigInt`, then multiplies by 1000. `receiptEligible` compares the **receipt timestamp** to the response's anchor clock. Receipt time and observation time may differ; do not substitute one for the other or gate receipts using the delayed vehicle display clock. Missing receipt timestamps or invalid anchors cannot become eligible.

`firstRepresentableMillisecond` calculates the ceiling of an exact microsecond timestamp, including negative timestamps before the epoch. A receipt at 52.7504 seconds is excluded at 52,750 ms and included at 52,751 ms. An exact-millisecond receipt is included at that millisecond. The returned boundary must itself fit a safe integer. These helpers do not replace backend checkpoint discovery or make the current API accept fractional clocks.

The interpolation core deliberately accepts safe-number microseconds. `safeObservationMicroseconds` bridges from the parser only when the integer is exactly representable; otherwise it returns `null` for the caller's contract fallback. Do not coerce a parser result with unchecked `Number()` or serialize internal `BigInt` values into JSON. Parser calendar support does not imply every date fits the interpolation core's numeric range.

## HTTP view boundary

The area route uses an explicit [view encoder](../../apps/api/view_encoding.py): timezone-aware datetime values are normalized to UTC and serialized with `Z`, retaining all six microsecond digits when present. FastAPI's default encoding of ordinary dictionaries previously emitted `+00:00`, which the strict parser correctly rejects. Retained weather reading/coverage/source times and planning receipt times enter the view as strings, so their declared fields are normalized explicitly too. Naive datetimes fail instead of inheriting the host timezone. This applies after snapshot composition, so domain events, persisted identities and original capture/evidence strings remain unchanged; pre-serialized event timestamps already use `Z`. Embedded capture evidence and the evidence endpoint retain original source representations.

The [HTTP contract test](../../apps/web/tests/exact-time-api.spec.ts) reads a real composed city response backed by imported PostGIS fixture inputs and passes its nested timestamps through the production parser and receipt-boundary helpers. It covers transport observations/receipts, weather, planning and composition. Existing UI date/time formatters are checked against equivalent `Z` and `+00:00` strings. A Python route regression also supplies a fractional observation through real fixture replay and verifies `.750400Z` survives HTTP serialization without changing subsequent replay results.

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

HTTP boundary regression validation: 185 affected Python unit cases passed across the final affected suites and reruns, plus nine real PostGIS tests. The 42 selected Playwright cases passed across the transport run and final weather/planning/HTTP-contract rerun. Ruff and mypy (77 source files) passed. The new contract test runs in the existing CI Playwright suite, including compiled serving smoke; no additional workflow is required. Docker smoke was not repeated for this boundary fix.

This is an implementation building block. Runtime freshness policy evaluation, comparison with the real server freshness function, v2 fixture/import/checkpoint migration, window selection, scheduler wiring and end-to-end seek/playback parity remain separate work under the accepted contract. The area view now uses the accepted canonical timestamp spelling; no freshness threshold, display delay, clock unit, route packaging or live-source policy changes here. Progress remains in the [delivery plan](../delivery-plan.md).

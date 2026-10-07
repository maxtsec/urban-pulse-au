# MAP-02: exact position freshness

The area snapshot now supplies the accepted `position_freshness_policy` with version `southbank-position-freshness-v1`. Its thresholds come directly from the same `POSITION_STALE_SECONDS` and `POSITION_EXPIRED_SECONDS` used by the server evaluator and checkpoint scheduler: stale at 120 seconds, expired at 300 seconds. This remains a fixture policy, not a live TTL decision. The parent field is additive; event identities, receipt history, clock units and checkpoint scheduling remain unchanged.

The server's [position evaluator](../../urbanpulse/location/city.py) uses integer timedelta components instead of floating-point seconds. The [browser evaluator](../../apps/web/src/animation/position-freshness.ts) uses the strict UTC parser and BigInt microseconds. It accepts the parent's latest observation and the current playhead, never a historical sample chosen for a delayed pose. A null or future observation is `unknown`; an invalid clock, observation or policy returns an explicit unavailable result so a future playback caller can retain the labelled static server view.

Policy validation checks the accepted version and safe, nonnegative integer thresholds with stale strictly before expired. Thresholds are read from the response, with no client defaults. Changing or approving a new policy still requires architecture review. Optional typing allows older snapshots to reach validation and fallback rather than acquiring an assumed policy.

## Verification

The [shared parity corpus](../../tests/fixtures/position-freshness-parity.json) contains 217 cases: years 1969, 1970, 2026 and 2100; observation fractions 0, 1, 400, 999, 1000 and 750400 microseconds; the millisecond immediately before, at and after the ceiling of the observation, stale and expiry boundaries; plus a null observation. Expected values express the accepted datetime boundary rules. The [Python test](../../tests/unit/test_position_freshness.py) checks every case against the production server evaluator; the [HTTP test](../../apps/web/tests/freshness-api.spec.ts) checks the browser with the same corpus and the policy read from a real PostGIS-backed area response. It also compares current API observations at replay seconds 0, 120, 300 and 360.

The frontend unit suite covers malformed/unsupported policies, unsafe clocks, missing/future observations, exact and fractional thresholds, supplied thresholds and deterministic local reevaluation of 100 staggered observations without mutating their parent. Server tests verify exact microsecond edges and that serialized thresholds come from the existing constants. The corpus test works in both local preview and compiled serving smoke without requiring a Python environment on the browser runner.

Reproduce with `pytest tests/unit/test_position_freshness.py`, `npm run test:unit` in `apps/web`, and `npx playwright test tests/freshness-api.spec.ts` against the normal local test services.

Validation: 54 affected Python unit tests, 16 image/workflow guard tests, all 190 local integration tests, 26 typed frontend unit tests and both timestamp/freshness HTTP Playwright tests passed. Ruff, mypy (77 source files), frontend lint/format/build and 853 local documentation links passed. Docker web-build smoke verified both complete build inventories and static export with the new file explicitly allowed. The 217-case corpus is checked by both language implementations; the HTTP check uses the policy actually returned by the server.

## Integration boundary

The helper is not yet connected to the current 15-second playback UI. It does not alter area assessment, source coverage, membership, cap or totals. Continuous playhead/window scheduling, applying dim/static/hidden display states, marker tallies and proving zero freshness-only requests during actual playback remain MAP-02 integration acceptance work. Progress is recorded in the [delivery plan](../delivery-plan.md).

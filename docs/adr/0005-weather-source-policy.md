# ADR 0005: Weather sources and warning assessment policy

Date: 2026-10-05

Decision: use the approved weather-source roles and warning assessment policy. Live-source enablement remains separate.

## Context

This decision extends [ADR 0003](0003-cloudevents-and-area-conditions.md). Implementation and source enablement are tracked in the [delivery plan](../delivery-plan.md).

UrbanPulse needs everyday weather information and applicable warnings while preserving source meaning. Open-Meteo model output, VicEmergency warnings and BOM station observations or warnings are different products. Adding a provider should preserve domain boundaries and provenance without requiring a speculative universal weather schema.

## Decision

### Scope and ownership

Keep one **Weather & Hazards** bounded context. Separate reading and warning responsibilities internally; aggregate boundaries and concrete persistence schemas follow their demonstrated identity, lifecycle and consistency needs.

Use Open-Meteo for labelled modelled weather information. It does not produce adverse facts, change Normal/Degraded/Unknown, or satisfy weather-warning coverage. Show it in a weather information section, separate from the slower planning profile. Forecast features remain a later option requiring scope approval.

Select VicEmergency as the candidate initial warning source, limited to verified weather-related warning products. The candidate products are severe weather, severe thunderstorm, riverine flood and flash flood warnings. Flood warnings are within the candidate scope; each product needs its own access, mapping, lifecycle, geography and completeness verification before enablement. Its `Met` category is a provider mapping to validate, not the domain definition or proof of exhaustive coverage. Fire, hazmat, road incidents and automatic emergency advice are outside this slice.

Keep BOM as a possible later addition after product access and use conditions are verified. A successful permission request does not approve a new product, severity mapping or source-selection policy automatically.

### Pilot conditions and warning severity

The current-condition inputs are transport service status and the agreed weather-warning product coverage. Modelled readings, forecasts, station observations, positions and planning do not substitute for either input in this pilot.

For the selected VicEmergency weather-warning slice, an applicable **Watch and Act** or **Emergency Warning** contributes an adverse fact only while effective and not cancelled, expired or superseded. Advice, including Threat Is Reduced, is informational: display it in the warning list, not in degradation reasons. This is an application condition policy, not a claim that Advice means safety. Preserve original warning text, level and source links; do not reuse this mapping for BOM products.

Validate geography and temporal applicability before contributing an adverse fact. A warning polygon describes the provider's warning applicability; intersection does not prove observed flooding or another physical impact in Southbank. Unrecognised categories or levels must remain explicit and cannot establish complete coverage.

### Coverage

Freshness and completeness are separate evidence. A recent fetch or HTTP success does not establish complete product coverage. An empty result supports no applicable active warning only when the source contract establishes a successful complete snapshot for the selected products, geography and relevant time, with update/cancellation semantics understood.

Without that evidence, weather-warning coverage stays unknown. A known applicable adverse fact still produces Degraded with incomplete coverage; without an adverse fact, incomplete required coverage produces Unknown. Normal requires both required inputs to be supported, fresh and complete under the accepted policy. Removing an expired warning does not repair missing coverage. Fresh model output cannot repair warning coverage.

### Integration and provider evolution

Capture permitted raw payloads and manifests before provider-specific normalisation. Replay starts from retained captures without fetching a provider again. Weather & Hazards owns its domain projections and publishes CloudEvents; Location Intelligence consumes those contracts and owns the area projection. It must not read Weather & Hazards tables or be called directly by a provider adapter.

Phase 2 uses shared in-process publisher/handler ports with reconciliation after restart or handler failure. Phase 3 adds durable delivery and publication recovery; this decision does not select a broker or approve a new capture transaction scheme.

Keep provider/product, provider record identity, source/effective/capture times, units, spatial precision and capture references as appropriate to each record. Preserve the distinction between modelled readings, forecasts and station observations. Original warning levels remain available beside any versioned application mapping.

Add providers through adapters and meaningful shared contract tests. Use additive, compatible migrations when a new product introduces a real concept. Do not relabel historical model output as station observations or promise that every provider change needs no migration.

Do not merge warnings across providers in the pilot. Keep each warning's provenance and lifecycle; two warnings may explain the same Degraded condition without numerical weighting. Same-provider duplicate, older-revision, update, cancellation and expiry handling remain mandatory. Combining provider coverage or choosing precedence requires a reviewed policy; two partial feeds do not imply complete coverage.

### Attribution

Apply the source register's [attribution acceptance and receipt-time definition](../source-register.md#attribution-acceptance) as CITY-02 requirements; embedded third-party content rights remain a source enablement gate.

## Consequences and validation

Source-specific access, retention, endpoint suitability, polling, supported products, snapshot completeness and live spatial/freshness evidence remain [source enablement gates](../source-register.md). This decision selects the design, not live access.

Use synthetic fixtures to demonstrate modelled weather without status changes, Advice without degradation, active applicable higher-level warnings with degradation, cancellation/expiry, unknown coverage, and duplicate/out-of-order delivery. Replaying a retained capture must not require network access. A later BOM adapter should pass the applicable shared contracts while preserving any product-specific meaning; demonstrate an outage without false recovery. Acceptance cases live in the [testing strategy](../testing-strategy.md) and [city demo](../demos/city-mvp.md).

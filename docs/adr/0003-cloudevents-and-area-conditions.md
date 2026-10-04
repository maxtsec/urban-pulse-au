# ADR 0003: CloudEvents and area conditions with separate coverage

Status: accepted by the project architect on 4 October 2026 for the two decisions below. Complements [ADR 0002](0002-southbank-tram-pilot.md).

## Context

The city MVP combines transport, weather and planning through in-process events before durable delivery. Its event format should survive that transition. A known tram disruption must remain visible when weather coverage is missing; missing data cannot justify a healthy area.

## Decision

Adopt **CloudEvents 1.0 structured JSON** for integration events, with UrbanPulse payload versions, aggregate revisions and capture references. Keep provider times explicit and separate from application acceptance time. Application ports use this format without requiring a broker or CloudEvents SDK. The [event contract](../architecture/capture-event-contract.md) specifies the initial profile and example.

Keep **current conditions and source coverage separate**. A known applicable adverse fact produces Degraded even when another required input is unknown. With no known adverse fact, incomplete required coverage produces Unknown. Normal requires all required current-condition inputs to be complete and current. Preserve reasons and input coverage alongside the condition; no numeric area score is selected.

## Consequences and remaining decisions

Use the same serializable boundary in phase 2 and phase 3. Format validation and revision comparison do not provide transactional deduplication, durable dispatch or crash recovery; those belong to the delivery adapters.

Location Intelligence evaluates accepted facts with an explicit clock and input policy. Source failure cannot itself resolve an adverse fact. Warning expiry removes that reason; incomplete coverage can still prevent a Normal result. Planning remains a separately explained area profile.

This ADR does not approve the proposed capture storage/recovery scheme, source-specific freshness or severity policies, spatial matching rules, map provider, timing targets or cloud host. Subsequent [ADR 0005](0005-weather-source-policy.md) accepts the pilot weather-source roles, VicEmergency severity mapping and required-input/coverage principles; its live-source gates remain separate. Review those details through A-01 to A-06. [Area semantics](../architecture/area-contract.md) distinguish the accepted principle from proposed pilot rules; the [delivery plan](../delivery-plan.md) owns progress.

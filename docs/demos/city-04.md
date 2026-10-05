# CITY-04: Shared events and restart recovery

Use the [city setup](city-01.md#run): start PostGIS, migrate, explicitly import the fixture, then run API/UI. The city scenario and map interactions remain the same. This slice makes composition and recovery inspectable through API events and tests.

## City story and events

1. Open `http://127.0.0.1:5173/?scenario=city`. Inspect tram service, weather warnings and the separate planning profile.
2. Read `/api/v1/areas/au-vic-melbourne-clue-southbank?scenario=weather-outage&seconds=239`. Conditions are Degraded by the retained warning, with source coverage kept separate.
3. Request 240 seconds: the warning expires without a new warning delivery. Conditions become Unknown; `composition.area_events` ends with that time-driven transition and original input references.
4. Request 241 seconds: evaluation time advances, but the same transition list remains. Rewind to 60 seconds; no later resolution/profile snapshot may appear.
5. Open a second browser tab with a different scenario/clock. Replay cursors are request-local. In the planning panel, inspect source dates, successful receipt and history independently of area conditions.

## Restart

At a selected clock, record the assessment, coverage events and area-event IDs. Stop only the API process, start it again using the setup command, then request the same URL. Reconstruction uses the selected normalized PostgreSQL import and produces the same result. The selected import is stored in PostgreSQL; the API needs no local pointer or raw payload files and does not call fixture normalizers during recovery.

City endpoints return 503 for an unavailable database or missing migration/import, preserving the UI's existing unavailable/retry flow. Restore the dependency, then retry. Do not remove shared local tables to simulate a failure.

## Automated failure evidence

```powershell
uv run --locked pytest tests/unit/test_delivery.py tests/unit/test_composition.py -q
uv run --locked pytest tests/integration/test_city_inputs.py -m integration -q
```

Tests inject a transient failure after candidate mutation, assert rollback of effect/receipt, and verify bounded retry without rerunning successful handlers. Integration tests interrupt an import, reimport concurrently, check corrupt-history rejection and start a fresh Python process after persistence but before dispatch. The fresh process forbids raw fixture reads and normalizer calls.

The dispatcher has no external side effects or durable queue. Restart repairs the city view from inputs; it does not establish delivery of every notification. The [evidence record](../evidence/city-04-composition.md) owns measured results and [ADR 0008](../adr/0008-in-process-city-composition.md) owns the decision.

For the equivalent container checks, use the [Compose setup and isolated smoke command](../development.md) and its [evidence](../evidence/city-04-compose.md). Basic `/health/ready` checks PostGIS/Redis rather than city import completeness.

# CITY-02: Southbank weather and warning replay

## Run and inspect

Use the [CITY-01 setup](city-01.md#run), including local PostGIS. Restart the API after updating fixture files; no provider key or network fetch is required. Open `/?scenario=weather` or select **Weather warnings** to see modelled temperature, rainfall and wind visible above the map. Use the visible scenario buttons to switch views; the active button is highlighted and keyboard accessible. Switching scenarios preserves the replay clock and map camera, pauses playback and updates `?scenario=` for reload/share and browser back/forward. A pending switch labels the previous view until the new snapshot arrives. Shared links select the scenario; a reload starts its clock at zero. The default City overview also includes the planning profile; this walkthrough isolates the weather slice. The existing tram controls and original transport scenarios remain available.

| Clock | What to inspect |
| --- | --- |
| 0s | Synthetic modelled temperature/rain/wind are visible, but incomplete warning coverage keeps conditions Unknown. |
| 30s | Advice polygon overlaps Southbank; it is informational. Complete authored coverage plus clear transport yields Normal. |
| 60s | Watch and Act plus the tram interruption yields two independent degradation reasons. |
| 90/105s | Original warning events are redelivered. Revision receipts prevent duplicate effects or rollback. |
| 120s | Identical warning payload is received again. Receipt time advances; warning update time, revision and original event provenance do not. |
| 150s | The received cancellation removes only the weather reason. Transport is still disrupted. |
| 180s | Transport clears; an applicable Emergency Warning becomes the remaining reason. |
| 210s | Authored source coverage becomes stale while the valid warning still gives Degraded. |
| 240s | Warning validity ends exactly here; coverage stays stale, so conditions become Unknown. |
| 270s | A new complete capture restores current coverage and Normal. |
| 300/330s | Unrecognised severity and missing geometry prevent a complete assessment. |
| 360s | Those warnings expire, but incomplete coverage does not repair itself. |

Open **Replay diagnostics** at 120s to inspect separate Transport and Weather counts; Weather reports two duplicates. If a weather scenario has no modelled reading yet, its summary says so while warning details remain available.

The desktop map and context panels stack independently with compact spacing. On mobile, the weather summary remains above the map. Toggle **Warning areas** without removing the accessible warning list. Rewind to 30s: the original Advice state and receipt time return without later cancellation information.

Press the **Weather outage** scenario button. The warning feed becomes unavailable at 90s; later captures, cancellation and coverage recovery are not received. The last known Watch and Act remains effective until 240s. It then expires, leaving Unknown with error coverage. Modelled readings cannot fill that gap. Attribution and the 60s receipt time remain visible.

The grey rectangles are authored warning polygons. Positive-area overlap establishes applicability, not an observed storm/flood footprint. Boundary-only contact is excluded under [ADR 0006](../adr/0006-weather-fixture-spatial-and-freshness.md).

## Acceptance and checks

Given identical retained captures and a clock, replay produces identical area conditions and evidence without provider access. Test cancellation/expiry boundaries, source outage, missing geography, unknown severity, partial product scope, repeated captures and conflicting/old event delivery. Validate containment, edge/vertex contact, holes and invalid geometry against real PostGIS.

Run `scripts/check.ps1` for unit/API, lint, types and build checks, then `scripts/check-city.ps1` for real spatial and Chromium browser checks. Browser screenshots are saved under `.local/city02/`; CI attaches them with the existing city evidence artifact.

See the [weather contract](../architecture/weather-fixture-contract.md), [dated evidence](../evidence/city-02-weather.md) and [delivery plan](../delivery-plan.md). Live provider access and source-use permissions remain a separate track.

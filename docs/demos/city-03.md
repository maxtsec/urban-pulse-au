# CITY-03: Integrated city and development profile

## Run

This walkthrough uses the development-only API-backed scenario harness, not the public synthetic explorer.

Follow the [local city setup](city-01.md#run), including PostGIS, and rerun the fixture import after updating fixture files. Open `http://127.0.0.1:5174/tests/scenario.html?scenario=city`. **City overview** combines tram positions, weather information/warnings and synthetic development sites. No provider key is used by this demo.

The source dates below are authored historical snapshot dates. The six-minute clock compresses capture attempts and failures; it does not imply monthly development changes occur within minutes.

| Clock | Inspect |
| --- | --- |
| 0s | Three developments inside Southbank with Applied, Approved and Under construction statuses. Snapshot as of 1 September; weather coverage is still unknown. A fourth located record is outside the area and excluded. |
| 60s | Planning snapshot redelivery appears as one duplicate. Transport and weather independently affect current conditions. |
| 90s | Identical planning payload recapture advances receipt only; the source date remains 1 September. |
| 120s | Partial capture preserves the previous list/date; planning coverage becomes unknown. |
| 150s | A complete 1 October snapshot changes original statuses, omits one prior record and adds an unlocated record. The panel confirms that the latest complete snapshot was received; spatial coverage remains unknown. Missing location stays off the map and outside the count; inspect retained absence history. |
| 180s | A malformed capture is rejected atomically; the profile and receipt remain at 150s. |
| 210/240s | Authored stale/error checkpoints keep the last complete profile visible. |
| 270s | A complete 2 October snapshot restores location coverage. Three developments appear; transport/weather support Normal. |

Select a building on the map or use the keyboard in the **Developments** tab to inspect source status, reported area, position and completion year in the selection card. Toggle **Development sites** under **Layers**; the accessible list remains available. The Overview tab links to the detailed list. Open **Replay diagnostics** for separate Transport, Weather and Planning outcomes. Timeline markers that share a second with a weather moment list both labels, for example **150s · Cancelled / New planning snapshot**.

Select **Planning outage** at 270s. Its planning timeline markers show the last successful receipt, outage onset and continued unavailability; they do not offer a new snapshot or recovery. The first profile remains available with error coverage and its original 1 September source date; later captures are suppressed. Current conditions stay Normal because planning is outside the current-condition inputs. Rewind to zero to reproduce the initial result. Scenario switching preserves the camera and clock; its URL supports reload/share, while reload starts at zero.

## Verification

Run `scripts/check.ps1` and `scripts/check-city.ps1`. Coverage includes contract/ordering failures, atomic absence handling, complete empty versus missing snapshots, real PostGIS point edges/vertices, rewind/restart, database-independent evidence, map/list selection, layer toggles, missing locations, source dates and mobile layout. Browser screenshots are written under `.local/city03/` and included in CI's city-browser-evidence artifact.

See the [contract](../architecture/planning-fixture-contract.md), [architect decision](../adr/0007-planning-fixture-profile.md), [evidence](../evidence/city-03-planning.md) and [delivery plan](../delivery-plan.md).

On narrow screens, the selected record appears in a bottom card that stays visible while the development list is scrolled. Close it with **Clear selection**.

# City MVP demonstration scenario

This acceptance scenario follows the [delivery milestones](../delivery-plan.md#milestones-and-exit-evidence). For the local toolchain walkthrough, use the [Phase 0 demo](phase-0.md).

## Product story

Open the Melbourne map and ask: **What is happening around my city right now, and how healthy is an area?**

Use the selected Southbank CLUE small area and Yarra Trams slice from [ADR 0002](../adr/0002-southbank-tram-pilot.md). The panel distinguishes current conditions from the area profile and shows timestamps, validity, source links and missing inputs.

## Scenario and expected outcomes

Use a deterministic synthetic scenario first, clearly labelled throughout. Fix the scenario clock; do not present old fixture timestamps as current live data. Final status categories and thresholds depend on the agreed contract.

| Step | Input/action                                                   | Expected visible result                                                                        | Engineering evidence                                                                         |
| ---- | -------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| 1    | Load baseline transport, warning coverage and planning records | Map layers and area facts with each source's coverage/as-of time                               | Capture references, spatial match and fixture label                                          |
| 1a   | Refresh successive tram positions for the Southbank view       | Vehicle markers move using source timestamps; stale positions are marked or withheld by policy | Stable IDs, coordinate validation, cadence/rate-budget evidence; synthetic playback labelled |
| 2    | Introduce a transport disruption                               | Transport facts and the agreed area explanation update                                         | Meaningful domain change and area projection trace                                           |
| 3    | Add an applicable severe-weather warning                       | Warning validity, available geography/precision and combined reasons appear                    | Spatial and temporal overlap, event identity                                                 |
| 4    | Inspect development records                                    | Planning activity is visible as longer-term context                                            | Source status and snapshot date; no invented positive/negative score                         |
| 5    | Replay the same update, then an older one                      | No duplicate effect or replacement by older state                                              | Consumer identity/ordering and replay tests                                                  |
| 6    | Make weather data stale or unavailable                         | Unknown/stale coverage is explicit; no false low-risk state                                    | Freshness clock and outage behavior                                                          |
| 7    | Expire or cancel a warning while transport remains disrupted   | Warning state changes; transport reason remains                                                | Time-driven recomputation and approved transition rules                                      |
| 8    | Select an area without planning coverage                       | The panel reports unsupported/missing data                                                     | Boundary/source coverage checks                                                              |
| 9    | Restore sources or reconnect the UI                            | A fresh snapshot reconciles current state                                                      | Reconnect/recovery path, no cache-created source freshness                                   |

Explain overlapping events using the [area semantics](../../project_brief.md#area-semantics): preserve evidence, uncertainty and the distinction between current conditions and area profile.

## Event and historical extensions

In phase 2, trace the agreed envelope through in-process publication and the Location Intelligence handler; verify duplicate/older inputs and restart recomputation. In phase 3, trace a domain update through publication intent, delivery, the idempotent Location Intelligence consumer and AreaStatusChanged. Stop a consumer, exercise retries/dead-letter handling, then replay and verify one final effect. Use the phase 1 CONTRACT-01 envelope for both delivery adapters; A-05 selects durable transport.

In phase 5, use captures retained since phases 1-2 to inspect a historical time range, explain sampling/coverage and trace a displayed result through its serving publication to dbt, BigQuery and retained raw inputs. Demonstrate a failed quality gate preserving the previous result. Current UI refresh must remain independent of a full warehouse rebuild.

## Recording evidence

Record the source commit/release, fixture or live mode, selected geography, source permissions, input identities/times, approved status rule version, test results and known limitations. Tie each completed phase demonstration to its Git tag. For reliability extensions, add event IDs, consumer attempts, failure injection, observed recovery and cleanup.

Label the demonstration mode and use the city MVP exit criteria in the delivery plan.

## Weather-source evolution demonstration

Follow [ADR 0005](../adr/0005-weather-source-policy.md), using synthetic captures until live source gates pass:

1. Replay an Open-Meteo-shaped modelled reading and show its source, effective time and label in weather information. Area status and warning coverage remain unchanged.
2. Replay an applicable active VicEmergency Watch and Act warning, including a synthetic riverine flood example: show the original level/link and a degradation reason. Display Advice separately without a degradation reason. Verify the source register's [attribution and receipt-time acceptance](../source-register.md#attribution-acceptance).
3. Compare a fresh but unverified empty snapshot with a verified complete empty in-scope snapshot. Only the latter can establish warning absence; Normal still requires complete current transport coverage and no adverse fact.
4. Disable provider access and replay retained payloads/manifests through normalisation, Weather & Hazards CloudEvents and Location Intelligence. Demonstrate update, duplicate, older revision, cancellation and timer-driven expiry.
5. When BOM access and a product-specific policy are accepted, add its adapter and run applicable shared contracts. Show its provenance alongside the existing provider, without cross-provider merging or relabelling old modelled data as station observations.
6. Interrupt a source: expose stale/unknown coverage and preserve unresolved applicable adverse facts. Verify the same [attribution acceptance](../source-register.md#attribution-acceptance) during outage and offline replay. Do not claim provider interchangeability when product semantics differ.

Demonstrate two successful captures of identical warning bytes: receipt time advances, while the warning revision and warning-change event count do not. Then contrast a failed capture and offline replay using the same receipt-time acceptance.

Exercise severe weather, severe thunderstorm, riverine flood and flash flood as separate candidate-product cases; mark unverified products explicitly and do not infer their coverage from the flood example. Show changed adapter/mapping code and any justified compatible migration alongside stable domain boundaries. Record actual results in dated evidence; the scenario does not imply these adapters already exist.

# CITY-04: City composition through shared events

Decision: [ADR 0008](../adr/0008-in-process-city-composition.md). Progress: [delivery plan](../delivery-plan.md).

## User outcome

The Southbank map, warnings and planning profile continue to tell one consistent city story after duplicate delivery, handler failure or application restart. Warning expiry and source coverage changes update the explanation even when no new warning content arrives. Planning stays separate from current conditions.

## Implementation sequence

1. Define the added typed fixture events and publisher/handler results; preserve existing envelope identities, revision guards and public snapshot responses.
2. Add the accepted persistence option, Alembic migration and explicit idempotent fixture import. Expose bounded domain export ports with capture observations and original event identities.
3. Route all three domains through the in-process publisher and Location handlers. Compose required coverage and condition changes in stable order; retain the existing spatial ports and accepted rules.
4. Add clock-driven evaluation, bounded retries, structured failure diagnostics and restart reconstruction. Preserve independent scenario clocks and the evidence endpoint's lightweight path.
5. Update local setup, demo and evidence; run unit/API, real PostGIS integration and Chromium browser checks before the feature PR is ready for implementation review.

## Acceptance cases

| Given / when | Then / verification |
| --- | --- |
| A typed event crosses the publisher boundary | A JSON round trip reaches the handler with the same identity, revision and payload; no ORM/provider objects cross the boundary. |
| The same event arrives twice, or changes only trace context / equivalent numeric spelling | One effect; duplicate diagnostics. Changed content under the same identity is rejected, including an old ID. |
| An older revision arrives after a newer one | Current state stays newer; the attempt remains visible as superseded. |
| An import fails halfway, or the same bundle is imported again | No partial readable scope after failure; one accepted copy of every event after reimport. Test against real PostgreSQL. |
| An unchanged warning payload is successfully captured again | Last-successful receipt can advance while warning identity/revision and source update time remain unchanged. |
| An active warning expires without further events | Its adverse effect ends at the fixture validity boundary; area reasons/coverage are recalculated from retained inputs. |
| A source becomes unavailable without a new domain change | Its coverage changes; known adverse facts remain visible under existing rules. |
| A handler fails before commit, then succeeds on retry | No partial effect or receipt; the original event applies once. Other successful handlers are not rerun. |
| A handler keeps failing | Attempts stop at the configured bound, diagnostics identify the failure and the snapshot is unavailable; a later healthy reconstruction succeeds. |
| The process stops after domain persistence but before dispatch | A fresh process reconstructs the same state from exports, with original event IDs, planning history and capture receipt times. |
| Two clients request different scenarios/clocks concurrently, then one rewinds | Each result matches an isolated reconstruction; no future resolution, coverage or planning state leaks into the earlier view. |
| A reason's input order changes, or only evaluation time advances without a semantic transition | No extra AreaStatusChanged event. A real required-coverage change is observable. |
| An object moves out of Southbank or a warning footprint changes | Recomputed membership removes the previous applicable effect; no stale area membership survives. |
| A new planning snapshot arrives while transport/weather stay the same | Profile changes, but planning cannot create an adverse fact or fill required current-condition coverage. |
| The API starts without migrations/imports or PostgreSQL becomes unavailable | City endpoint returns 503 with setup guidance; basic readiness checks only dependencies. No automatic migration/import on GET or falsely successful city snapshot. |

Real integration tests use isolated database scopes. The restart test must discard all in-memory objects and reconstruct in a fresh process; replaying the original JSON directly does not establish persisted-domain recovery. Browser checks retain map camera/selection behavior, scenario URLs, rewind and separate domain diagnostics.

## Demonstration plan

Replay the integrated city timeline through a disruption and warning, show duplicate attempts without duplicate effects, advance past warning expiry, then stop and restart the application at a selected clock. Compare state, original receipt times and planning history. Use a test-only injected handler failure to show bounded retry and recovery; do not expose an unauthenticated failure-control endpoint.

## Independent source work

SRC-02 can prepare bounded transport access verification while this decision is reviewed. Check the active authentication header, documented quota scope, compatible static IDs and observed cadence. Keep credentials server-side and exclude real payloads from public fixtures. A successful access probe does not approve continuous capture, retention, source completeness or cloud deployment; those gates remain in the [source register](../source-register.md).

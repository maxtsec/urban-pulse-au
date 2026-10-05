# Weather fixture contract

CITY-02 implements the [source policy](../adr/0005-weather-source-policy.md) and [spatial/freshness decision](../adr/0006-weather-fixture-spatial-and-freshness.md). This contract is reviewed with its feature PR. It describes synthetic v1 records; SRC-02 must establish actual provider schemas and access before a live adapter is enabled.

## Boundaries and capture

The existing content-addressed city bundle includes `weather-scenario.json`: authored raw payloads, per-attempt capture IDs/times, product scope, success/completeness declarations, readings, explicit coverage checkpoints and delivery attempts. The bundle digest verifies retained bytes. Per-attempt IDs refer to records within that immutable bundle, not independently uploaded cloud objects. Payload SHA-256 values make identical recaptures inspectable.

Application replay passes raw records through a fixture normalization port. Its adapter creates published CloudEvents; Location Intelligence consumes those contracts through its projection and spatial port. No provider adapter calls area rules or reads area tables. Replay rebuilds bounded state from retained history at a request-local clock. A new request can rewind without leaking later cancellations or captures.

This is a fixture normalizer, not an implementation of either provider's wire format. Provider revisions and change IDs are authored inputs, not an approved live source-ordering algorithm. The current in-memory call path is not the shared publisher/handler adapter, persistent reconciliation or durable delivery work assigned to CITY-04/EVENT-01.

## Published payloads

Both events use the existing CloudEvents 1.0 envelope, weather producer namespace, revision/receipt guard and provenance fields. Live/fixture namespaces remain distinct.

| Type | Identity and state |
| --- | --- |
| `au.urbanpulse.weather.warning-changed.v1` | Subject equals `provider/product/record_id` and `warning_id`. Full warning state: original level, headline/text, issue/update/cancellation times, source URL, polygon or explicit unknown precision. Effective start/end are mandatory for this fixture profile. |
| `au.urbanpulse.weather.modelled-reading-changed.v1` | Provider/product/record-scoped reading ID, `kind=modelled`, model identity, valid time, longitude/latitude, temperature °C, rainfall mm, wind km/h and source URL. It never supplies warning coverage or adverse facts. |

Warning source-update time agrees with provenance; issue cannot follow update, cancellation cannot precede issue or follow update, and acceptance cannot precede update. Invalid intervals, identities, coordinates, Unicode and non-finite numbers are rejected. Missing geometry and unrecognised original levels/products stay explicit instead of being coerced into safe values. Only the VicEmergency policy has a severity mapping; equivalent text from another provider is not automatically mapped.

Full-state warning revisions replace earlier severity, geometry and validity. Same source/event ID with changed content is Conflict; exact redelivery is Duplicate even after a newer revision. Older revisions cannot restore cancelled warnings. Cancellation is known only after its captured update; expiry is calculated from already received validity, without inventing a new provider event.

## Receipt and coverage

A new, valid capture of identical raw bytes preserves the original warning event and capture provenance while advancing independent receipt evidence. Readings and warning records retain their original source times. Malformed captures are rejected before partial application and do not advance the last successful receipt. Semantic uncertainty may still be a received capture, but cannot establish complete coverage.

A complete synthetic warning snapshot must include severe weather, severe thunderstorm, riverine flood and flash flood in its declared product scope. Additional declared products do not invalidate coverage of those four; unrecognised warning records still cannot establish complete coverage. Unknown levels/products, unknown applicability, conflicting/older records or an absent still-active known record make coverage unknown. An omitted warning is never treated as cancellation. Once a snapshot is incomplete, expiry alone cannot make it complete; a new supported complete capture is required. An explicit outage retains known facts until their received validity ends, while source coverage remains error.

Checkpoint labels are a fixture teaching mechanism, not a live freshness guarantee. Successful empty, complete coverage can support Normal only when transport coverage is also current and there are no active adverse facts.

## Area API and UI

The existing area endpoint accepts additional `weather` and `weather-outage` scenarios and returns an additive nullable `weather` section. It contains modelled information, warning lifecycles/applicability, independent receipt/source times, coverage and policy IDs, attribution, projection outcomes and captured evidence. Original transport scenarios keep `weather=null`.

Warning membership uses the pinned area revision. Weather changes also change the immutable bundle digest and city projection version. Cached spatial results depend on both geometries; conditions, expiry and coverage are recomputed at each requested clock.

Map shading represents active warning polygons; the list also preserves cancelled/expired records. Every warning view keeps original severity/text and source links. The page shows State of Victoria, the EMV notice link and the original fixture receipt date/time with Melbourne timezone. Open-Meteo is credited alongside explicitly synthetic modelled readings. No external map/provider request is made by fixture execution.


The evidence endpoint reads the same normalized capture timeline without running transport/weather projections or spatial queries. It remains available during a spatial-service outage. An absent capture identity returns 404; malformed bundle references, integrity failures or unavailable storage return 503 without exposing internal details. Invalid provider records inside a structurally valid capture remain explicit rejected attempts.

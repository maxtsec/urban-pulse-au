# Capture and integration-event contract

CloudEvents 1.0 is accepted in [ADR 0003](../adr/0003-cloudevents-and-area-conditions.md). The initial UrbanPulse wire profile below is accepted; capture storage/recovery and handler design remain A-03 proposals. It prepares CONTRACT-01 and the parallel capture track. [Area semantics](area-contract.md) define the consuming view; [delivery status](../delivery-plan.md) owns implementation progress.

## Weather provider boundary

[ADR 0005](../adr/0005-weather-source-policy.md) requires capture before provider-specific normalisation and replay from retained payloads/manifests. Weather & Hazards publishes domain facts through this envelope for Location Intelligence; provider wire formats and database tables do not cross that boundary. Modelled readings, forecasts and station observations retain distinct meaning. Warning identity includes its provider/product scope; do not merge identities across providers. Same-provider redelivery and revision rules still apply. Concrete weather payload schemas remain CONTRACT-01 work.

## Separate three identities

| Identity | Meaning | Retry/replay rule |
| --- | --- | --- |
| Capture ID | One upstream fetch attempt, allocated before the request | A new request gets a new ID, even for identical bytes; retrying storage for that attempt reuses its ID |
| Payload SHA-256 | Integrity of the exact retained bytes | Equal bytes have equal hashes; this does not make two observations or attempts identical |
| Domain/event identity | One accepted record change within its producer and aggregate | Redelivery/replay of that change preserves its event ID and aggregate revision |

The existing worker's file hash is a smoke-path content identity. Do not extend it into the production capture ID: identical feeds fetched at different times still need separate evidence of capture success and source age.

## Capture-only record and recovery

Propose one durable intent record before each provider request. It identifies the capture ID, fixture/live mode, provider/product, endpoint alias, request start and collector version. Store no key, authorization header or credential-bearing URL. Each attempt terminates with an immutable manifest: captured, fetch-failed, raw-write-failed or abandoned after reconciliation.

A captured manifest contains its schema version, request/completion times, HTTP status, source timestamp when present, content type, byte count, payload hash and immutable object locator/generation. Missing source time is null with an explicit reason. Format/parser/static-schedule versions and processing outcomes belong to a separate processing record; collection need not wait for schema interpretation or a running API/database.

Use a capture-specific raw prefix containing mode, provider, product, UTC date and capture ID. Write intent, payload and terminal manifest with create-only semantics. [GCS generation preconditions](https://docs.cloud.google.com/storage/docs/request-preconditions) support conditional creation; adapters must verify an existing object's identity/hash after a conflict rather than accepting arbitrary bytes. Keep raw objects private. Lifecycle and accepted retention duration must account for incomplete intents and replay evidence.

| Interruption | Reconciliation outcome |
| --- | --- |
| Before provider request | Intent records an abandoned attempt; no success is inferred |
| Provider response received but raw write fails | Mark failure; do not advance source freshness or a domain projection |
| Payload stored but manifest missing | Reconstruct a manifest only from validated retained intent/object metadata; otherwise quarantine the orphan |
| Manifest exists but normalization has not run | Queue/replay processing from the retained capture; capture itself remains successful |
| Same capture storage operation retried | Verify existing content; one terminal capture outcome |
| Same bytes fetched again | New capture ID, same content hash; no duplicate domain change or refreshed observation timestamp. Successful receipt follows the [source receipt-time policy](../source-register.md#attribution-acceptance), independently of domain revision |

Persist recovery metadata needed to reconstruct the manifest with the payload at write time. A failed request is never replayed as if it produced a payload. A single active collector plus a durable lease/fencing and shared quota design must handle restart/rollout overlap before CLOUD-01 acceptance; an instance count of one alone is insufficient. Exact lease/storage implementation is reviewed with A-06.

## Payload storage options for A-03

The capture-specific payload layout above is a baseline proposal. Compare it with content-addressed payload objects referenced by per-attempt manifests before selecting the storage adapter. Keep a distinct capture ID, request outcome and timestamps for every attempt in either design; payload reuse must not reset source age or merge capture evidence.

Content-addressed storage can reuse identical feed bytes, especially unchanged alerts. Scope keys by fixture/live mode and source-use boundary as well as content hash. Review concurrent writes, integrity checks, orphan recovery and reference-aware garbage collection: a shared payload must remain available while any retained manifest requires it. A simple object-age lifecycle rule can break newer manifests that reference older objects.

Evaluate lossless compression, including gzip over protobuf payloads, using representative permitted samples. Measure byte savings and CPU cost instead of assuming a fixed compression ratio. Record encoding, uncompressed length/hash and stored-object length/hash; replay must recover the exact originally hashed payload bytes. Already compressed responses require an explicit transport-decoding policy. Bound decompression output and reject corrupt payloads.

Deduplication and compression are separate choices. Neither changes domain/event identity. The A-03 decision must include replay fidelity, retention/reference cleanup and recovery tests before either optimisation is enabled.

## CloudEvents envelope and UrbanPulse profile

Use the [CloudEvents 1.0 specification](https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md) and its [structured JSON format](https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/formats/json-format.md). CloudEvents standardizes the outer context, not our delivery guarantee or business schema. Wire `specversion` is `1.0`; `source` plus `id` identifies an event. Use application-owned payload types and ports without a mandatory CloudEvents SDK or a broker dependency.

| Field | UrbanPulse meaning |
| --- | --- |
| specversion, id, source, type | CloudEvents context; type includes the payload major version |
| subject | Stable domain aggregate identity, namespaced by provider/product where needed |
| time | UTC time the application accepted the meaningful change; provider/effective times stay explicit in data |
| datacontenttype | application/json |
| upmode | fixture or live; also isolated in the producer namespace |
| data.revision | Positive monotonic application revision within source + subject; not a provider timestamp |
| data.schema_version | Payload contract version; independent of the envelope specification |
| data.provenance | Provider/product/record, capture references and source-time evidence |
| data.effective_from / effective_until | Explicit validity, nullable only where the event-specific contract permits |
| data.correlation_id / causation_id | Processing relationships; never an assertion of real-world weather causation |
| data.state | Full published aggregate state for this event type; no ORM, cloud SDK or broker objects |

Synthetic v1 position envelope, shared with the executable fixture:

```json
{
  "specversion": "1.0",
  "id": "synthetic-position-change-2",
  "source": "urn:urbanpulse:fixture:transport",
  "type": "au.urbanpulse.transport.vehicle-position-changed.v1",
  "subject": "yarra-trams/synthetic-vehicle-1",
  "time": "2026-10-04T00:00:30Z",
  "datacontenttype": "application/json",
  "upmode": "fixture",
  "data": {
    "schema_version": "1.0",
    "revision": 2,
    "provenance": {
      "provider": "synthetic",
      "product": "tram-positions",
      "record_id": "synthetic-vehicle-1",
      "capture_ids": ["synthetic-capture-2"],
      "source_observed_at": "2026-10-04T00:00:25Z"
    },
    "effective_from": "2026-10-04T00:00:25Z",
    "effective_until": null,
    "correlation_id": "synthetic-scenario-1",
    "causation_id": null,
    "state": {
      "vehicle_id": "yarra-trams/synthetic-vehicle-1",
      "route_id": "synthetic-route-1",
      "position": {"longitude": 144.96, "latitude": -37.824},
      "observed_at": "2026-10-04T00:00:25Z"
    }
  }
}
```

Persist a new event ID with its accepted revision; retry dispatch with those exact values. Rebuilding a projection uses the preserved accepted history and its ordering rules, not newly generated revisions for old inputs. Source ordering is resolved before incrementing the application revision: older observations do not replace newer ones; equal source revision/time with conflicting content is quarantined unless the source supplies an explicit correction rule. Missing or ambiguous ordering evidence cannot become a newer current record merely because it arrived later.

## Payload and handler boundaries

Transport publishes position and service-status changes separately. A position includes a source-scoped vehicle identity, nullable route/trip references, validated coordinates and optional observed time. `subject` must exactly equal `data.state.vehicle_id`, including its namespace (for example, `yarra-trams/synthetic-vehicle-1`); `provenance.record_id` retains the upstream record identity. The position's `effective_from`, `observed_at` and provenance `source_observed_at` must agree, including null when observation time is unknown. For position events, `effective_until` must be null. This is not unlimited freshness: consumers calculate age from `observed_at` using the versioned area freshness policy; missing observation time stays unknown. A producer cannot supply a deadline to keep an old marker current. Capture references must be unique. Never substitute a GTFS entity ID for a stable vehicle ID without source evidence. Unknown identities stay isolated from canonical vehicle history. Service status retains affected stops/routes, declared coverage and provider validity; delay values preserve negative, zero and missing meanings.

Weather publishes validity/cancellation and declared spatial precision. Planning publishes complete current record state plus snapshot identity/as-of time; missing records become removals only after a complete successful snapshot under the approved policy. AreaStatusChanged publishes condition reasons **and coverage** with boundary/rule versions, input projection revisions and evaluation time. Timer-driven changes can cite earlier inputs without inventing a new provider capture.

The publisher port accepts a serialized-compatible event; each handler returns applied, duplicate, superseded, retryable-failure or rejected with a reason. Deduplication keys include handler identity and event source/ID. Apply the effect and record the outcome consistently. Equal aggregate revision with different content is a conflict, not a successful duplicate. Full-state events permit a newer revision to supersede an older one, while preserving audit evidence.

Location Intelligence consumes published domain snapshots through ports; it does not query another context's private tables. Reconcile both old and new spatial memberships when a record moves. If prior membership is unavailable, rebuild the pilot view from the published snapshots. Use input revision checks so a slow old recomputation cannot overwrite a newer area snapshot.

Phase 2 uses the same envelope in process with bounded retries and explicit failed-handler evidence. Restart/failure triggers recomputation from persisted domain state. Phase 3 adds durable publication intent, consumer state and acknowledgements behind adapters. Neither the envelope nor an in-memory handler proves crash-safe delivery.

## Compatibility and test cases

Within payload major v1, optional additions must not change existing meanings. Consumers tolerate unknown optional fields, preserve them when forwarding and reject unsupported major versions. Producers must not introduce required semantics under a minor version: a receiver cannot detect an undocumented semantic change from its version number alone. Required-field or semantic changes need a new event type major and a migration/replay plan. Keep the envelope version separate from payload and projection versions.

The initial executable profile lives in `urbanpulse/contracts/events.py`: UTC-normalized timestamps, explicit payload nulls, typed positions, capture provenance and fixture/live producer isolation. Unknown envelope extensions use CloudEvents primary JSON mappings: strings, signed 32-bit integers and booleans. A null extension is treated as absent; floating-point attributes and nested extension structures are rejected. Context strings, including `id`, `subject` and extensions, reject control characters, Unicode noncharacters and unpaired surrogates. The shared Identifier type applies the same constraints to payload identifiers. All wire-model strings and nested optional keys/values reject unpaired surrogates before acceptance, including Python constructor inputs; valid surrogate pairs normalize to their Unicode character. Free-form payload text retains valid JSON controls and noncharacters, without inheriting the stricter context-string rules. Binary, URI and timestamp extensions travel as strings; an extension-specific contract must define their additional semantics or any secondary mapping.

The revision guard compares a SHA-256 of sorted-key JSON from the validated model, excluding only top-level `traceparent` and `tracestate`. Tracing fields remain in serialized events. Equal integral numbers such as `1` and `1.0`, including signed zero, have the same fingerprint recursively; booleans, strings and different numeric values remain distinct. Non-finite numbers are rejected before serialization. Other context fields and the complete `data` payload, including optional additions and payload nulls, participate in conflict detection. This is an internal normalized fingerprint, not a cross-language canonical JSON standard.

A handler must look up retained receipts by `(source, event ID)` and pass a found `prior_receipt` to `compare_revision` before considering the aggregate cursor. An exact retained event is Duplicate even after newer revisions; changed content, subject or revision under the same event identity is Conflict. Without a retained receipt, the guard can only compare with the latest aggregate cursor and may classify an older revision as Superseded. The pure function does not retain history: the delivery adapter must implement a receipt ledger with an explicit retention window and atomic effect/receipt storage. It cannot guarantee conflict detection outside retained history.

CONTRACT-01 acceptance also requires shared publisher/handler contracts and source-specific payloads. Cover roundtrip with nulls and UTC timestamps; missing/invalid fields and future versions; repeated captures versus storage retry; duplicate events; older revisions; equal-revision conflicts; failure then retry; same observations with newer fetch times; fixture/live isolation; warning expiry without incoming events; and stale recomputation losing to a newer projection. Real storage/transaction/crash tests accompany the adapters that introduce those boundaries.

# Normalized Tram history: Phase 1a contract

Status: **Proposed for architect review.** The required field coverage and delivery order were specified on 2026-10-08; row grain, keys and physical schema below make the first export reviewable before implementation. This is analytical history, not the existing city-event/animation contract. Proposed schema version: `tram-normalized-v1`.

## Grain and required fields

Use separate Parquet tables, with explicit schemas even when empty. Keep capture evidence distinct from observations so failures and repeated unchanged feeds remain measurable.

| Table | Row grain | Required columns (nullable source values remain present as columns) |
| --- | --- | --- |
| `captures` | One finalized source capture | `store_id`, `capture_id`, `capture_sequence`, `feed`, `requested_at`, `received_at`, `completed_at`, `outcome`, `http_status`, `failure_reason`, `raw_sha256`, `receipt_sha256`, `feed_timestamp`, `gtfs_realtime_version`, `incrementality`, `entity_count`, `normalizer_revision` |
| `vehicle_positions` | One VehiclePosition entity occurrence in a capture | Common lineage below; `vehicle_id`, `trip_id`, `route_id`, `start_date`, `service_date`, `start_time`, `direction_id`, `trip_schedule_relationship`, `observed_at`, `received_at`, `latitude`, `longitude`, `bearing`, `speed`, `current_stop_sequence`, `stop_id`, `current_status` |
| `trip_updates` | One TripUpdate entity occurrence in a capture | Common lineage; `vehicle_id`, `trip_id`, `route_id`, `start_date`, `service_date`, `start_time`, `direction_id`, `trip_schedule_relationship`, `observed_at`, `received_at`, `trip_delay_seconds`, `stop_update_count` |
| `stop_time_updates` | One StopTimeUpdate occurrence within a TripUpdate | Parent update ID and common lineage; `stop_update_ordinal`, `stop_id`, `stop_sequence`, `stop_schedule_relationship`, `arrival_present`, `arrival_time`, `arrival_delay_seconds`, `arrival_uncertainty_seconds`, `departure_present`, `departure_time`, `departure_delay_seconds`, `departure_uncertainty_seconds` |
| `quality_issues` | One retained diagnostic for an entity/field | Capture/entity/stop references, fixed reason code, source field and relevant raw capture pin; do not copy credentials or arbitrary exception text |
| `area_memberships` | One observation-to-area evaluation for each selected area | `observation_id`, `area_id`, `area_revision`, `static_revision`, `membership` (`inside`, `outside`, `unknown`), `method`, unresolved reason |

Common lineage is `schema_version`, `normalizer_revision`, `store_id`, `capture_id`, `capture_sequence`, `raw_sha256`, `entity_id`, `entity_ordinal`, `record_id`, `static_revision`, `area_revision`. Stop rows also retain `service_date`, `start_date`, `start_time`, `observed_at` and `received_at` from their parent for independent partitioned queries. A TripUpdate with zero stop updates still produces a parent row. Repeated visits to one stop cannot be keyed by stop ID alone. Keep tombstone/deletion entities as capture diagnostics until their analytical treatment is implemented; do not silently drop them or call that capture fully normalized.

## Types and source semantics

Identifiers/enums: UTF-8 strings (retain enum numeric code as an additional integer where necessary); IDs are never coerced to numbers. Coordinates/speed/bearing: Float64, finite and within source-defined range. Sequences/counts/delays/uncertainties: signed Int64 where applicable. Times: Parquet UTC timestamp at microsecond precision; dates: Date; presence flags: Boolean. Use null for absent protobuf fields, preserving explicit zero and absent submessages separately. Invalid source values produce diagnostics with the raw reference; never substitute zero or a current time.

`service_date` is the parsed local service calendar date from TripDescriptor `start_date`; also retain the source `YYYYMMDD` string. `start_time` is a separate service-time string that may exceed 24:00:00. Neither is derived from UTC observation/receipt date. Missing or invalid source service dates stay null with an explicit issue, not a guessed partition. Agency timezone comes from the pinned static feed, not the host timezone.

`observed_at` comes only from the matching VehiclePosition/TripUpdate timestamp. Keep `feed_timestamp` separately; it cannot silently fill a missing entity timestamp. `received_at` comes from the original immutable capture receipt. Stop arrival/departure Unix times are predictions from the source, not proof of actual arrivals; preserve both their time and delay even when both are present. Trip-level and stop-level schedule relationships remain separate. Later derived/imputed values require separate columns and a named policy.

These mappings follow the [GTFS Realtime reference](https://gtfs.org/documentation/realtime/reference/) and [GTFS service-time definitions](https://gtfs.org/documentation/schedule/reference/). The references govern source meaning; this document's row layout and identifiers are UrbanPulse proposals.

## Identity, scope and repeatability

Construct record identity from schema/normalizer revision, store UUID, capture UUID, entity ordinal and (for child rows) stop-update ordinal using canonical serialization and SHA-256. Entity IDs remain source fields; duplicates within a feed are retained and flagged. Byte-identical records from distinct captures retain distinct capture provenance. Removing repeated provider observations is a later, explicit staging-model rule, not deletion of capture evidence.

Process only finalized captures at a fixed high-water sequence; do not acquire the collector's exclusive journal lock or modify its checkpoint. Pin exact capture manifests, source payload hashes, static tram-member hash and both area boundary revisions in the export manifest. Use the accepted Southbank/CBD boundary policy for positions; use pinned trip/stop linkage for updates. Unknown linkage remains unresolved with raw retained. Do not pretend an unresolved record belongs outside the selected areas. Distinct areas share observation rows through the membership table rather than duplicating source records.

Each export describes a half-open UTC receipt interval and its corresponding local-day label/timezone, capture high-water mark, actual coverage, rejected/unresolved counts, input inventory hashes and table schemas. The first one-day export cannot claim 24-hour coverage before that much data exists; a calendar-day export can include explicit pre-activation gaps. Sort table rows by stable record keys and compare values/nulls/precision, not only row counts. Volatile export creation time belongs in the manifest, not the data rows used for rebuild comparison.

## One-off Parquet and upload acceptance

1. Run a bounded offline normalizer on the encrypted host data, with no provider calls and no collector restart. Write Parquet and its manifest to a separate encrypted output directory. Preserve the source raw bytes and all unresolved records.
2. Rebuild the same pinned interval and compare every row/column in stable order. Inspect required-field presence, null/zero behavior, midnight and missing-service-date cases, duplicate entities and repeated-stop updates. Pin normalizer/library versions; Parquet binary identity is not assumed across library versions.
3. Perform one reviewed export upload using the existing collector SA and its existing objectCreator capability, without IAM expansion. Keep the [ADR 0018 confirmation protocol](../adr/0018-capture-delivery-and-expiry.md#upload-and-metadata-confirmation): create-only objects, durable pending state before upload, independent service checksums and generation-bound confirmation. The existing scoped `objects.get` remains available only for that accepted confirmation workflow.
4. Respect current delivery-contract bounds: objects at most 8 MiB and pending records at most 32 capture pins. A day is a bounded set of chunks plus manifests, not one oversized object/pending record. Design a bounded manifest tree if needed; do not silently increase persistent limits. Record object generations, checksums, row counts and source interval; no automatic recurring upload is enabled by this one-off acceptance.

## Raw expiry gate

Keep raw expiry disabled. Required position and stop-level TripUpdate fields must first survive source decoding, Parquet round-trip, upload confirmation and warehouse loading with tests. This is necessary, not sufficient: accepted raw retention, complete normalization of all required products (including alerts), unresolved/quarantine clearance, confirmation and verification holds from ADR 0018 still apply. An export or a successful mart does not alone authorize raw deletion.

Phase 1b then develops the first mart/publication; Phase 1c automates normalization/upload after this contract and one-off path are accepted. [Delivery order](../delivery-plan.md#data-pipeline-priority-track).

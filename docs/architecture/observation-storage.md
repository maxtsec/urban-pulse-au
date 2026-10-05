# Versioned observation storage

[ADR 0009](../adr/0009-durable-event-delivery.md) accepts the EVENT-01 delivery design. This storage boundary preserves normalized input history used by both city replay and later durable publication. Progress belongs to the [delivery plan](../delivery-plan.md).

## Format and ownership

Each owner-specific observation row has an explicit integer `codec_version`. Version 2 interprets only these top-level slots:

| Owner | Single nullable event | Event lists |
| --- | --- | --- |
| Transport | `event` | None |
| Weather | None | `events`, `warning_records` |
| Planning | `event` | None |

Frame, evidence, rejected-header and other ordinary JSON fields are opaque to reference decoding. Their keys may include `event_reference`, `rejected_event`, `kind`, `source` or `id`, at any nesting depth. Unknown storage versions, missing event slots, malformed descriptors and missing revisions fail explicitly.

An accepted event slot stores `{"kind":"reference","source":"...","id":"..."}`. A semantically identical resend with different serialized context also retains its original `attempt_envelope` string. A rejected identity/revision conflict stores `{"kind":"rejected","envelope":"..."}` so replay can reproduce that rejection. Receipts still verify attempt identity/content against the referenced accepted envelope. No domain revision, event ID, capture ID, trace context or observation order changes with the storage version.

The codec handles row shape and event slots; owning repositories handle revision lookup and integrity. Serving and import share this boundary. Storage-version changes are distinct from normalizer-version changes: this migration changes representation without changing normalized content or import identity.

## Upgrade and rollback

Stop old API/import processes before running `uv run --locked python -m urbanpulse.adapters.city_store migrate`, then restart them using the updated code. This is a coordinated fixture-schema upgrade, not a rolling deployment. Compose initialization uses the same migration. No raw recapture or reimport is required for an already selected, valid import.

Migration `0003_observation_codec` freezes its conversion logic independently of the runtime codec. For each supported `city-normalizer-v2` import, it resolves only the declared legacy slots, verifies the complete normalized-content checksum and converts descriptors in the same PostgreSQL transaction as its schema changes. Missing/ambiguous references or content mismatches roll back the upgrade. Envelopes, fingerprints, metadata, content hashes and the active-import selection remain unchanged. Run the migration while fixture writers are stopped; it locks and scans retained supported history.

Older unsupported normalizer exports retain their original bytes with `codec_version=1`; they remain unavailable under the existing normalizer gate. They are neither silently upgraded nor deleted. New imports use version 2. Unknown future normalizer/version combinations cannot be downgraded into an ambiguous legacy representation.

Downgrade converts version 2 back only when every opaque value is safe for the old recursive reader and the content checksum still matches. A literal legacy tag in frame/evidence blocks downgrade and leaves all schema/data unchanged. Resolve such cases through a separately reviewed data-preservation plan; do not delete metadata to make rollback pass.

## Verification

Use `uv run --locked pytest tests/integration/test_observation_migration.py -m integration -q` with local PostgreSQL available. Tests create unique schemas without a public-schema fallback and remove only those schemas. Independently written legacy fixtures cover full transport/weather/planning history, duplicate/rejected attempts, original trace context, active selection, safe round trips, failure rollback and preserved unsupported imports.

The normal integration suite checks literal fields in newly written observations, corruption rejection, reimport identity and city/evidence equivalence. [Verification evidence](../evidence/event-01-observation-storage.md) records the measured result.

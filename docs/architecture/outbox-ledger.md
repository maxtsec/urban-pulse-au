# Outbox and consumer ledger

Decision: accepted option A in [ADR 0009](../adr/0009-durable-event-delivery.md). Progress and remaining work: [delivery plan](../delivery-plan.md). This is the transaction/repository slice of EVENT-01.

## Boundaries

`EventStore` and `EventTransaction` are application ports. `PostgresEventStore` owns READ COMMITTED transactions; owner-specific SQL repositories bind to the same adapter connection. A producer saves its domain state and calls `publish` inside that unit of work. Normal exit commits both; an exception rolls both back. A failed publication/consumption operation poisons the unit of work even if its exception is caught inside the block.

Consumers receive the original serialized envelope. Their effect callback must write through repositories bound to that same transaction, including any derived publication. It must not commit the connection, use an independent database connection, perform network side effects or recursively process another claim. Application handlers do not import SQLAlchemy or the event tables; adapter wiring binds their repositories to the transaction.

Browser requests and the existing fixture import do not enqueue events. The accepted fixture-run producer and Location Intelligence worker are wired in later implementation slices; these primitives are verified with database-local test effects.

## Publication identity

A publication is unique by `(context, source, event ID)` and by `(context, source, subject, revision)`. Semantic fingerprints use the existing CloudEvents receipt rules, excluding delivery trace context and normalizing numeric representations. A resend returns the original publication ID and preserves the first wire bytes. Changing semantic content, reusing an aggregate revision under a different ID or changing the registered consumer set raises `PublicationConflict` and aborts the transaction.

Consumers are a nonempty, unique set. Publication plus one pending delivery per consumer commit atomically. The set is frozen at publication time; adding a consumer later needs the separately implemented explicit backfill operation. Contexts and versioned consumer names are internal ASCII identifiers up to 200 characters; durable revisions fit a positive signed 64-bit integer. Fixture-run context construction remains part of the run-coordinator slice.

## Claims and attempts

Claims select up to 100 eligible deliveries for one consumer using `FOR UPDATE OF deliveries SKIP LOCKED`, then commit a lease and attempt record before returning. Claims include context, consumer, delivery identity, generation and deadline. Normal lease duration is 30 seconds; callers can choose a positive duration up to one hour. PostgreSQL wall time owns expiry.

A later claim sweep can reclaim an expired lease with a new generation. Each expired lease retains its attempt outcome and consumes one of three automatic attempts. After the third expiry, the next sweep marks the delivery dead-letter with `attempts-exhausted`. Another consumer's delivery is independent. An empty claim batch is not evidence that a run has completed; it can contain locked, leased or just-exhausted work.

This layer does not implement timed retry after an explicit handler failure, worker polling, lease renewal, operator replay or an ordered fixture-checkpoint barrier. It does not promise global queue ordering. The worker/recovery slice adds persisted retry scheduling and diagnostic operations before the city run coordinator depends on them.

## Completion and receipts

Completion locks the delivery and verifies its context, consumer, generation and current lease against stored values. It validates the stored publication against its receipt metadata. The same transaction checks event-ID receipts before aggregate revision ordering, applies a new current effect, advances the aggregate cursor, records the receipt, and completes the delivery/attempt. A derived event published by the callback shares that commit.

Duplicate/superseded events skip the effect. Reusing an old ID with changed content is conflict even after a newer revision; the prior receipt stays unchanged. Conflict during claimed completion becomes a terminal dead-letter outcome. An exact repeat of already committed completion returns its stored outcome without invoking the effect again.

Lease validity is checked before processing and again before writing completion. An expired/replaced claim cannot commit an effect through this boundary. Failures roll back effect, receipt, cursor and derived publications; the already committed claim/attempt remains available for expiry recovery.

For the bounded pilot, advisory transaction locks serialize publications per context and receipts/effects per context plus consumer. Distinct consumer contexts can progress independently. These deliberately coarse locks cover first-ever identities and cross-subject event-ID conflicts. Multi-context transactions can still encounter database deadlocks; propagate/roll back the whole transaction, and let the later worker scheduling layer retry. Do not add in-transaction network waits.

## Migration and verification

Run `uv run --locked python -m urbanpulse.adapters.city_store migrate` to apply additive migration `0004_outbox_ledger`. It creates publication, delivery, attempt, receipt and cursor tables without backfilling work, switching active imports or changing city history. The existing API does not require a running delivery worker. Explicit downgrade removes these delivery records; it does not delete city imports. Preserve any needed delivery history before a separately requested downgrade.

Run `uv run --locked pytest tests/integration/test_event_store.py -m integration -q`. Tests create isolated schemas and real concurrent database connections, covering producer/effect rollback, first-publication races, independent claims, SKIP LOCKED behavior, repeated acknowledgement, receipt identity, expiry/generation fencing and exhausted leases. [Evidence](../evidence/event-01-outbox-ledger.md) distinguishes these transaction checks from later worker/process-crash evidence.

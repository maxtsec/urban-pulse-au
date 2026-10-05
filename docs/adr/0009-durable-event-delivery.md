# ADR 0009: Durable event delivery and consumer recovery

Date: 2026-10-05

Status: **Accepted by the project architect: option A, including its persistent delivery model and fixture-run scope.**

## Problem

CITY-04 persists domain inputs and rebuilds isolated projections in process. A worker crash after a domain commit can be repaired by reconstruction, but there is no durable record that a particular consumer still needs an event. EVENT-01 must make publication intent, retries, consumer effects and recovery observable across separate processes while preserving CloudEvents and the existing city replay interface.

## Options

| Option | Mechanism | Benefits | Trade-offs |
| --- | --- | --- | --- |
| **A: PostgreSQL outbox and consumer ledger (recommended)** | Commit publication intent with domain changes; independent workers poll durable per-consumer deliveries and commit effects with receipts. | Reuses the current database; deterministic local crash/concurrency tests; no new cloud service needed for the first slice. | Polling and backlog share database capacity; application owns scheduling, retry, dead-letter and replay tooling. |
| B: PostgreSQL outbox and GCP Pub/Sub | A relay publishes committed outbox records; subscriptions feed consumers that retain database receipts and effects. | Broker buffering and independently operated subscriptions; suitable when consumers require separate scaling or isolation. | Adds relay/acknowledgement failure boundaries, cloud identity and service configuration, and real-service acceptance work. The outbox and consumer idempotency are still needed. |

Recommendation A is an engineering judgment for the bounded pilot and current single-database deployment. Revisit B when measured database queue load, consumer isolation or independent deployment requirements justify it. Neither option selects cloud hosting or a live source-use policy.

PostgreSQL documents `SKIP LOCKED` for competing consumers of queue-like tables, while warning against treating skipped rows as a consistent general-purpose read. Use it only for work claims; domain reconstruction keeps its existing consistent reads. [PostgreSQL 17 locking clauses](https://www.postgresql.org/docs/17/sql-select.html#SQL-FOR-UPDATE-SHARE).

Pub/Sub defaults to at-least-once delivery without ordering guarantees. Its exactly-once feature does not remove publish-side duplicates, so application event identity and database transactions remain necessary. [Subscription semantics](https://docs.cloud.google.com/pubsub/docs/subscription-overview#default_subscription_properties), [exactly-once limitations](https://docs.cloud.google.com/pubsub/docs/exactly-once-delivery#things_to_know).

## Decision: option A

### Transaction and ownership boundaries

Keep database operations in adapters and transaction coordination behind application ports. Do not make domain objects or API routes depend on queue tables. Keep the synchronous CITY-04 adapter available for request-local replay; durable publication gets its own asynchronous enqueue/worker interface because enqueue success cannot mean every handler has completed.

A producer transaction saves its domain revision and publication intent together. A consumer transaction saves its effect, semantic receipt and terminal delivery outcome together; if that effect creates another integration event, its outbox row belongs to that same transaction. Acknowledgement occurs only after commit. Initially all effects are database-local; external notifications require a separately designed idempotent delivery boundary.

The initial persistent records are:

| Record | Responsibility |
| --- | --- |
| Publication | Immutable original envelope, semantic fingerprint, owner, source/event identity and publication context; unique within that context. |
| Consumer delivery | Independent pending/leased/retry/complete/dead-letter state for each registered consumer and publication. |
| Attempt | Attempt identity, lease generation, start/end, outcome and safe failure category; survives process restarts. |
| Consumer receipt and effect | Consumer version/context plus source/event identity and fingerprint, committed atomically with the consumer-owned state. |
| Fixture run | Import scope, scenario, rule/boundary versions, ordered checkpoint cursor and run identity for the bounded recovery demonstration. |

Register the initial consumers explicitly when publishing and create their deliveries atomically with the publication. New consumers use an explicit backfill operation; a shared global sent flag cannot represent independent consumer progress.

### Claims, retries and duplicates

Claim a bounded batch in a short transaction with row locking, then commit a lease and attempt before processing. Completion must verify the current lease generation and expiry inside the effect transaction. An expired or replaced worker cannot commit an effect. Serialize concurrent effects for the same consumer aggregate and enforce unique receipt/event identities in the database.

Check a previously seen event ID and its fingerprint before aggregate revision ordering. An old ID with altered content is a conflict; a semantically identical resend is duplicate even with a new tracing context. Preserve the existing superseded-revision rules for genuinely different older events.

Use persisted retry scheduling rather than sleeping inside a transaction. Fixture recovery-test policy: three total automatic attempts with 1-second then 5-second delays and a configurable 30-second lease. These are local recovery-test defaults, not production SLOs. Lease expiry consumes an attempt; exhausted or terminal failures enter a durable dead-letter state. Invalid/conflicting envelopes are terminal. A dead-letter event blocks only the dependent ordered fixture lane; other consumers/runs continue.

An explicit replay command records an operator reason and a new attempt generation while retaining original event identity, bytes and previous attempts. Replaying an already applied event must produce no extra effect. Correcting payload content requires a new valid domain revision, not editing history. No destructive retention or automatic dead-letter deletion is introduced; fixture cleanup removes an explicitly selected whole run.

### Fixture clock and demonstration boundary

Keep browser scenario/clock requests read-only and independently rewindable. They must never enqueue messages or move a durable consumer backwards.

Create a durable demonstration run explicitly from a selected normalized import. Its producer advances a stored receipt-clock checkpoint monotonically, saving each published revision/coverage change and its cursor atomically. Producer staging is separate from API import selection. At each checkpoint, a consumer applies all required inputs before publishing the resulting area status; pending or dead-lettered input prevents advertising that checkpoint as complete. Checkpoint controls and timer work are application records, not invented upstream observations.

Persist expiry/freshness work so restarting without a new upstream message still evaluates the due boundary. The demonstration must compare the resulting area condition, reasons, coverage and planning profile with the existing in-process replay at the same clock. Identical semantic transitions retain their existing event identity; run identity scopes delivery and receipts rather than altering domain payloads. Transport and weather determine conditions; planning remains a separate profile.

## Migration and existing follow-ups

Use additive Alembic migrations. Existing city imports and GET behavior remain usable without a running delivery worker. Preparing a durable fixture run from an existing import is an explicit command with version/integrity checks, not an automatic migration backfill.

Before durable publication consumes arbitrary observation fields, replace recursive `event_reference` key detection with a versioned observation codec that only decodes declared event slots and treats frame/evidence dictionaries as opaque data. Migrate old stored observations transactionally and verify identity, rejected-attempt history and content hashes; an ambiguous legacy record must fail explicitly rather than be guessed. This migration needs its own review and compatibility tests.

Keep the [measured CITY-04 request costs](../evidence/city-04-compose.md) as the benchmark baseline. Input caching and incremental reconstruction require complete scope/version keys, request isolation and explicit database-failure behavior. Replacing deep-copy must retain failed-attempt rollback, including planning history and receipts. These optimizations are separate reviewable changes; choosing a delivery transport does not silently authorize changed replay semantics.

## Acceptance and decision boundary

The [EVENT-01 specification](../architecture/event-01-durable-delivery.md) defines crash points, concurrency, retry/dead-letter, controlled replay and city-equivalence evidence. Option A is accepted. Implement the sequence through separately reviewed PRs; implementation progress stays in the delivery plan. Cloud resources and live source-use decisions remain separate.

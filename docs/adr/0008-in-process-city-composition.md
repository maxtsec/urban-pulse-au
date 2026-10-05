# ADR 0008: In-process city composition and restart recovery

Date: 2026-10-05

Status: **Accepted by the project architect**: option A and its fixture event/retry scope.

## Problem

The three fixture slices rebuild separate projections for every request. They validate events but do not share a publisher/handler path or persist normalized domain state. CITY-04 must demonstrate cross-domain composition, duplicate handling, time-driven changes and restart recovery while preserving independent replay clocks.

## Options

| Option | Recovery and receipts | Trade-off |
| --- | --- | --- |
| **A: Persist domain history; rebuild disposable projections (recommended)** | PostgreSQL keeps accepted domain revisions and capture/coverage observations. Each reconstruction has its own in-memory effect/receipt state. Restart reads published domain exports and rebuilds it. | Meets the phase 2 recovery requirement with a small persistent model; bounded fixture reconstruction remains necessary. |
| B: Persist domain history, area projections and handler receipts | PostgreSQL transactions commit each projection effect with its receipt. Restart also validates/reconciles the saved projection. | Reduces repeated projection work, but introduces consumer migrations, concurrency and receipt retention before EVENT-01. |
| C: Keep only retained raw fixtures | Restart normalizes the original bundle and rebuilds everything in memory. | Smallest change, but postpones the delivery plan's persisted-domain-state requirement and would require changing that acceptance criterion. |

## Decision: option A

Use the already selected PostgreSQL, SQLAlchemy and Alembic stack. Keep delivery synchronous and in process. The accepted scope covers the persistent input model and fixture event additions below.

### Ownership and persistent inputs

Transport, Weather and Planning own their accepted revisions and capture observations. Location Intelligence reads versioned export ports, never another domain's private tables. Database clients and migrations stay in adapters; application code coordinates transactions through ports.

The first migration creates fixture-scoped input history, with these logical records:

| Record | Identity and retained values |
| --- | --- |
| Fixture import | Bundle hash, normalizer version and schema version; atomically marked complete only after validation and import finish |
| Domain revision | Import scope, owning domain, source + event ID, subject, revision, original acceptance time, original serialized envelope and semantic fingerprint |
| Capture observation / replay attempt | Import scope, domain, stable attempt ID and receipt order/time, original capture references, accepted event references or rejection, completeness/product coverage and authored availability state |

Use owner-specific repositories and tables. Within an import, enforce unique event identity and aggregate revision; same identity with different semantic content is a conflict. Reimporting the same verified bundle is idempotent. Keep canonical envelope text so JSONB number conversion cannot alter replayed values; queryable metadata is stored separately. Trace context remains excluded from semantic fingerprints under the existing contract.

Store full accepted planning snapshots, including historical rows needed for the removed-record view. Preserve successful unchanged captures separately from domain changes so receipt time and coverage can advance without a new warning revision. Preserve duplicate, superseded and rejected fixture attempts as diagnostic inputs without accepting their contents as current domain state.

Import the bounded synthetic bundle in one transaction. A failed import leaves no readable partial scope. Retain the complete fixture import until an explicit local reset removes that whole scope; partial pruning is unsupported. This does not select a live retention policy, cloud capture layout or general-purpose event store.

### Published events

Keep the existing position, warning, modelled-reading and planning-snapshot envelopes. Add these fixture contracts, using the same CloudEvents profile:

| Event | Required published meaning |
| --- | --- |
| `TransportServiceStatusChanged` | Source-scoped service/stop identity, clear/disrupted state, stable disruption episode ID and start, latest observed time, reason and stop coordinates. A later disrupted update preserves episode identity/start. Resolution is published only when its clearing frame is received. |
| `SourceCoverageChanged` | Producer-owned input identity, capture attempt, last successful receipt, explicit completeness and product scope, authored availability state and references to the domain revisions represented. A failed attempt preserves prior successful receipt; an unchanged successful capture may advance it. |
| `AreaStatusChanged` | Area identity, condition, sorted reasons and required-input coverage, boundary/rule versions, contributing input revisions and evaluation time. Timer changes cite existing inputs and never invent captures. Planning remains a separate profile and cannot degrade conditions. |

Validate subject/payload identity and time consistency for every added envelope. The [capture/event contract](../architecture/capture-event-contract.md#city-04-fixture-publications-and-recovery) describes typed payloads and aggregate scope. These additions are fixture contracts, not verified live provider semantics.

Publish serialized JSON through a port and decode/validate at handler entry. Handlers return applied, duplicate, superseded, retryable-failure or rejected with a reason. Identity/content conflicts are rejected with an explicit conflict diagnostic. Malformed or unknown event types never mutate a projection.

### Replay isolation and time

Persist inputs once, then select them through an as-of export bounded by the requested fixture receipt clock and scenario policy. Future captures, resolutions and profile replacements must remain inaccessible to the current view even though the full synthetic bundle is stored.

Every reconstruction has a context containing import scope, scenario-policy version/hash, boundary revision, rule version and requested clock. Projection state, receipts and retries belong to that context; no mutable global replay cursor is shared between requests. Different browsers can use different clocks or rewind independently. This version keeps reconstruction request-local; a later cache must use the complete context as its key.

A reconstruction reads one consistent database view. Apply received inputs in stable receipt order through the publisher/handler path, evaluating time transitions between inputs and at the requested clock. The fixture clock drives expiry/freshness without requiring a new domain event. Rewinding rebuilds the earlier view rather than moving a durable aggregate backwards. Existing fixture freshness rules are exercised without accepting ADR 0004 or selecting live TTLs.

Use a stable ordered input-revision vector for recomputation. An area change is emitted when condition, reasons or required-input coverage changes, not merely because evaluation time, input order or trace context changes. Deterministic transition identity/revision is scoped to the fixture timeline and rule/boundary versions, so rebuilding the same inputs produces the same area events. Replaying a derived event to an external subscriber is outside this phase's delivery guarantee.

### Failures and reconciliation

In-memory handler effects and receipts commit together by applying to a candidate state, then replacing the current state only on success. Receipt identity includes reconstruction context, handler, source and event ID. Failed handlers must leave both state and receipts untouched; retry uses the original envelope. Earlier successful handlers are not rerun when a later handler retries.

Use at most three attempts per transient handler failure, with an injected delay policy (100 ms, then 250 ms). Tests use a fake sleeper. Validation/conflict outcomes are terminal. The dispatcher cannot retry irreversible external side effects in CITY-04; all handlers operate on disposable local projections.

After exhausted retries, discard the incomplete reconstruction and record structured failure diagnostics containing context, handler/event identity, attempt count and reason. Return an unavailable response instead of a partial current snapshot. A subsequent request or process restart rebuilds from PostgreSQL exports, including capture/coverage observations. Database errors likewise cannot silently fall back to a successful fixture result.

Domain state is committed before dispatch. A crash in that gap is repaired by rebuilding from persisted domain state; there is no promise that every event notification is delivered. Persistent consumer receipts, automatic durable retry, an outbox, broker choice, acknowledgements and DLQ remain EVENT-01/A-05 decisions.

## Acceptance and consequences

The [CITY-04 implementation specification](../architecture/city-04-composition.md) owns acceptance cases and the demonstration plan. The public HTTP snapshot/clock interface and existing UI interactions remain compatible. Add migrations and an explicit local import command, with database readiness explaining missing schema/imports; a GET request must not run migrations or import data.

Option A deliberately trades bounded reconstruction work for straightforward isolation and recovery. Measure the fixture request cost in integration evidence before adding projection caching or moving to option B. Existing source-use, live freshness, durable delivery and cloud decisions remain independently reviewable.

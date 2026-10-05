# EVENT-01: Durable city event delivery

Decision: [ADR 0009](../adr/0009-durable-event-delivery.md), accepted option A under A-05. Progress: [delivery plan](../delivery-plan.md).

## User outcome

A tram disruption or weather warning committed before a worker stops can still reach Location Intelligence after restart. A retry does not create duplicate reasons or planning history. The demonstration explains pending, retrying and dead-lettered work instead of presenting incomplete state as a healthy area.

## Implementation sequence after acceptance

1. Replace ambiguous observation-reference storage with a versioned codec and test migration of existing imports. Preserve original capture/envelope identity and permit literal `event_reference` fields in frame/evidence data.
2. Add publication, per-consumer delivery/attempt and receipt repositories with explicit transaction ports. Prove producer rollback, unique identities and concurrent claims using real PostgreSQL.
3. Add a separate worker and atomic consumer effects, scheduled retries, lease fencing and dead-letter inspection/replay. Keep network side effects outside this initial scope.
4. Add explicit fixture-run creation/advance commands, persisted timer checkpoints and a Location Intelligence consumer. Compare each completed checkpoint against the synchronous city replay; API reads must not publish.
5. Add reproducible process-crash and Compose evidence, then measure growing planning history and request reconstruction before a separate performance change.

Each implementation PR includes tests and awaits review. The existing map/slider remains available throughout; this work does not enable live collection or provision cloud services.

## Acceptance cases

| Given / when | Required result |
| --- | --- |
| Producer fails before committing domain change and outbox | Neither becomes visible. Retry creates one publication and one delivery per consumer. |
| Producer commits and dies before a worker sees it | Another process later consumes the committed intent; no in-memory pointer is required. |
| Two workers claim concurrently | One current lease per delivery; unrelated work can progress. |
| Worker dies after claiming or lease expires | Attempt remains recorded; work is reclaimable, and the old generation cannot commit an effect. |
| Handler writes an effect and fails before receipt commit | Effect and receipt both roll back. The retry applies once. |
| Worker dies after effect/receipt commit but before acknowledging | Redelivery finds the receipt and adds no second effect or derived publication. |
| Same event is resent with a different trace context | Duplicate, with original event/capture provenance retained. |
| Old event ID is resent with changed content | Conflict recorded before revision ordering; no overwritten state. |
| A genuinely older revision arrives after a newer one | Superseded; newer state remains authoritative. |
| A transient failure is scheduled, then all workers restart | Persisted next-attempt time and attempt count are honored; no reset of retry budget. |
| Three automatic attempts fail, or an envelope is invalid | Durable dead-letter outcome and diagnostic; dependent checkpoint is incomplete. |
| An operator replays a dead letter or an already applied event | Original bytes/identity and previous attempts remain; a replay reason is recorded; no duplicate committed effect. |
| One consumer fails while another succeeds | Their delivery/receipt states remain independent. |
| Worker restarts across warning expiry without a new capture | Persisted timer work evaluates the appropriate clock; expiry never invents a new source observation. |
| Full integrated city run reaches each completed checkpoint | Condition, reasons, required coverage and planning profile match synchronous replay; future frames never leak. |
| Two browser clients use different clocks or rewind | GETs enqueue nothing, share no mutable cursor and retain current UI behavior. |
| Migration reads historical imports with duplicate/rejected attempts | Identity and replay results are unchanged; literal reference-looking fields stay ordinary data. |

Use separate operating-system processes for crash tests and real PostgreSQL for transaction/concurrency tests. Inject failure at named test seams; do not expose an unauthenticated HTTP failure or replay endpoint. Store sanitized diagnostics with context, consumer, event identity, attempt/generation and reason. Track backlog age/count, retry count and dead letters without high-cardinality event IDs as metric labels.

## Review artifacts

Include migration/upgrade steps, a CLI/Compose recovery walkthrough, exact check results and bounded timing evidence. Record pending versus completed checkpoint semantics and the first retained run, and demonstrate database-unavailable behavior. Numeric live latency targets, cloud hosting and source retention remain independent decisions.

# Planning fixture contract

Design basis: [ADR 0007](../adr/0007-planning-fixture-profile.md), the [capture/event contract](capture-event-contract.md) and the [area contract](area-contract.md). [Delivery status](../delivery-plan.md) owns implementation progress.

## Scope and ownership

The fixture adapter normalizes authored DAM-shaped records. Location Intelligence consumes the published snapshot and computes area membership through its spatial port. API routes only compose the application service. Neither the application nor browser fetches a planning provider. Synthetic names, positions and source dates make no claim about actual development sites.

Planning is a slow area profile. Keep the original status text, development key, reported CLUE area, nullable point and nullable completion year. Unrecognised statuses remain visible verbatim; no severity, activity score or implicit status mapping is added. Coordinates are WGS84 longitude/latitude; missing coordinates remain null and invalid coordinates reject the capture.

## Published snapshot

`au.urbanpulse.planning.snapshot-published.v1` uses the existing CloudEvents envelope with `source=urn:urbanpulse:fixture:planning`. Its stable aggregate is `city-of-melbourne/development-activity-monitor/synthetic-pilot`, matching `subject`, payload scope and provider/product/record provenance. The pilot scope is an authored bounded sample, not a claim that all municipal developments were retrieved.

Payload state contains `snapshot_id`, nullable `as_of`, `complete=true` and up to 1,000 full records. Development keys must be unique. Record ordering is normalized by key before receipt comparison. Snapshot identity cannot be reused for different content. Atomic publication preserves the selected whole-snapshot absence rule without relying on partially delivered per-record changes. Splitting live publication or changing scope requires a separately reviewed contract.

`provenance.source_observed_at` equals the dataset snapshot's `as_of`, including null. It is not a per-record status-change timestamp. Source dates cannot follow receipt; both effective interval fields are null. A higher application revision cannot regress an already-known source date, remove a known date, or replace different snapshot content at the same source date. Ambiguous ordering is a conflict and preserves the previous profile. An initial unknown source date remains visibly unknown.

Use the existing revision guard and retained event receipts: exact redelivery is Duplicate, unseen older revisions are Superseded, and changed content under the same event ID is Conflict. Each accepted snapshot remains in bounded replay history. Same payload recapture advances the complete receipt timestamp without inventing another snapshot event or moving its source date.

## Fixture coverage scope

The bounded synthetic snapshot has one conservative spatial-completeness check: **any current record without coordinates leaves planning coverage unknown**, regardless of its reported `clue_small_area`. This deliberately includes a record labelled Carlton, Southbank or with no area label. A provider label is not verified spatial exclusion, so it cannot silently remove uncertainty from the selected area. Removed historical records do not affect this check. All unlocated current records remain visible separately, outside the map and Southbank count.

This is the fixture's declared rule, not a suitable automatic whole-municipality live policy. Before live DAM enablement, SRC-02 must verify and review area-scoped completeness or a trustworthy exclusion rule; a missing coordinate elsewhere could otherwise keep Southbank unknown indefinitely.

Capture acceptance and profile coverage are separate: `capture_state` reports current/unknown/stale/error from the received attempt/checkpoint; `state` additionally reflects missing source dates and unresolved spatial membership. At 150s, snapshot 2 is successfully accepted (`capture_state=current`) while its missing location leaves `state=unknown`. At 180s the next capture is rejected (`capture_state=unknown`), so the same accepted snapshot is retained. The panel describes these cases separately.

## Capture failures and evidence

A partial capture applies no rows. A malformed complete payload, duplicate key or invalid row rejects the entire snapshot. Neither advances the last successful receipt or removes prior records. A complete successful empty snapshot is distinct from no snapshot. Coverage checkpoints can assert only unknown/stale/error, not successful capture. Their timing is authored; there is no numerical live freshness policy.

For a newly accepted full snapshot, replace current records atomically and recompute current spatial membership. Keep missing prior records in the history view with their last listed status/date. Reappearing keys return to the current list. The membership of a removed record uses its last known position; it cannot establish its present position.

Weather and planning share capture timing, canonical payload hashing and an atomic normalization history for recapture/original-event redelivery. Domain-specific validation and completeness remain separate. Evidence reads the same normalized timeline without projections or database access. Missing capture identity returns 404; broken bundle references or capture integrity/storage errors return 503. Rejected provider-shaped payloads remain explicit evidence attempts. Never reveal frames beyond the selected clock; source outage blocks later captures and recovery until the non-outage scenario is selected.

## Area response and UI

The existing `planning` object retains `state`, `as_of` and `description`, with additive `capture_state` in integrated scenarios. The `city` and `planning-outage` scenarios add current `records`, `unlocated_records`, `removed_records`, snapshot identity/history, last successful receipt, policy identifiers, attribution, projection outcomes and evidence. Original scenarios retain the disconnected planning profile. Weather and transport remain independently replayed in the integrated scenarios.

The default **City overview** shows all three domains. Development sites use a separate building marker layer and accessible list with synchronized selection. Original statuses, snapshot dates and receipt times are separate labels. Missing locations never produce invented markers; missing source dates do not become receipt dates. Complete profile coverage can be current while current area conditions remain Unknown, and a planning outage cannot degrade otherwise Normal current conditions.

The field model is credited to [City of Melbourne DAM](https://data.melbourne.vic.gov.au/explore/dataset/development-activity-monitor/) with its [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) link and an explicit synthetic-modification label. Live use and retention are not enabled by this fixture.

## Acceptance cases

| Given / when | Expected result |
| --- | --- |
| First complete snapshot | Located developments appear with original status and source date. |
| Point on area edge/vertex | Included; a point immediately outside is excluded without a buffer. |
| Same capture bytes received again | Receipt advances; source date, snapshot event and profile stay unchanged. |
| Partial, malformed or failed next capture | Previous profile survives; coverage is explicit; no inferred removals. |
| Complete newer snapshot omits a record | Current list removes it; history retains its previous status without cancellation/completion inference. |
| Development moves outside the area | Membership updates; it is not reported as absent from its source snapshot. |
| Missing location/source date | Unknown stays explicit; location cannot contribute a Southbank count. |
| Duplicate/older/conflicting event | No duplicate effect or rollback; diagnostics retain the outcome. |
| Rewind or restart from retained bundle | Identical profile and evidence at the same clock. |
| Planning update/failure with fixed transport/weather | Current condition and reasons remain unchanged. |

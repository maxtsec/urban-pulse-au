# ADR 0007: Planning fixture scope, membership and snapshot absence

Date: 2026-10-05

Status: **Accepted by the project architect** for the fixture policies below.

## Decision

Use synthetic records modelled on the City of Melbourne Development Activity Monitor (DAM) for CITY-03. Keep source statuses and snapshot as-of dates visible. DAM represents major development context, not all development, verified current construction impacts or road incidents. Live API access, retention and identity continuity remain SRC-02 decisions.

A located development belongs to the Southbank CLUE area when `ST_Covers(area, point)` is true, including edge and vertex contact. Apply no distance buffer. Missing coordinates remain explicitly unlocated and are excluded from the map and the Southbank count; the provider's area label cannot replace spatial evidence.

Only a successful complete snapshot may remove an absent record from the current list. Preserve its prior state and retained snapshot evidence, label it **No longer listed in this snapshot**, and infer neither cancellation nor completion. Partial, rejected or failed captures preserve the last complete profile. A record that moves outside the boundary is spatially excluded rather than treated as absent from the source.

Planning updates remain separate from current conditions under ADR 0003. Neither a development count nor an original development status creates an adverse fact, supplies transport/weather coverage or changes Normal/Degraded/Unknown.

## Consequences

Keep source as-of time independent from capture receipt time and completion year. The fixture can replay receipt failures quickly while keeping its authored historical source dates; it does not simulate monthly developments occurring within minutes. Missing source dates and spatial uncertainty stay explicit.

The implementation publishes a bounded complete snapshot atomically so missing-record handling cannot act on partially accepted rows. The [fixture contract](../architecture/planning-fixture-contract.md) defines its executable payload and acceptance cases. Publication/handler wiring remains CITY-04; this fixture does not introduce a live source contract or durable delivery.

This decision accepts planning point membership only. Transport freshness/map policy is independently recorded in [ADR 0004](0004-southbank-fixture-map.md); this planning decision does not change it or define a live planning TTL.

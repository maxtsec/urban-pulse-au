# Early capture: hosting options

A-06 decision proposal, researched 4 October 2026. Evaluate continuous capture as part of the complete city application, reserving capacity for serving, storage, recovery and analytics. Melbourne was the initial regional preference; alternative regions and hosts remain options for architect review. Progress belongs in the [delivery plan](../delivery-plan.md).

## Hosting choices

| Option | Relative cost and operational trade-off | Validation before selection |
| --- | --- | --- |
| Local development | Lowest cloud overhead; collection depends on the developer machine remaining available | Record capture gaps; distinguish local demonstrations from a continuously available service |
| GCP free-tier collector in an eligible US region | Lower compute overhead; networking, excess storage and transfer remain billable; application hosting is separate | Confirm eligibility, source-use/regional constraints, memory headroom and transfer patterns |
| Small GCP VM in Melbourne | Regional placement with continuously allocated compute, disk and network resources | Measure collector footprint and leave capacity for later application workloads |
| Cloud Run worker pool | Managed container operation with continuous allocation; fewer host administration tasks | Measure runtime requirements and compare the complete recurring footprint |
| Shared demonstration host, including a lower-cost VPS | Amortises runtime overhead across collector, API, PostGIS and Redis; shared capacity and one failure domain | Architect acceptance of provider/region, concurrent-load tests, patching, backups and restore |

Domain boundaries remain separate even when processes share a host. Collection must continue independently of API/database availability, with raw inputs retrievable after host loss. Keep analytical development local until a separately evaluated cloud batch path is justified. No hosting option is selected by this comparison.

## DEMO-01 and Phase 4 boundary

[ADR 0010](../adr/0010-hosted-fixture-demo.md) proposes a fixture-only VM first. It does not select shared capture hosting under A-06. Adding CLOUD-01 requires approved source/retention policy, measured combined capacity, independent lifecycle and enforceable credential isolation; otherwise use a separate collector host. Application deployments must preserve collection continuity. CLOUD-02 adopts capture buckets, identities and manifests/checkpoints through infrastructure state; a serving-host migration does not justify rebuilding raw history. ADR 0010 defines the interim host's exit and migration acceptance.

## Workload assumptions

Use measured payload sizes and memory/CPU observations before sizing a deployment. An initial comparison scenario uses tram positions every 30 seconds and updates/alerts every 60 seconds: four requests per minute. At an assumed average payload of 1 MiB and 30-day retention, this produces 172,800 captures and 168.75 GiB of retained payloads at steady state. These values are planning inputs, not measured source characteristics or an accepted retention policy.

The baseline intent, payload and terminal-manifest scheme needs at least three writes per successful capture. A-03 also evaluates [shared payload objects and compression](capture-event-contract.md#payload-storage-options-for-a-03); remeasure bytes and operation counts after selecting the design. Include lease/retry operations, logs, reads, secrets, image/build storage, database backups and transfer in the evaluation. Static GTFS and other source products need their own cadence and size measurements. Soft deletion/versioning can retain billable bytes after lifecycle deletion.

Avoid bulk cross-region history downloads when evaluating network overhead. A shared host also needs disk-growth and backup capacity checks; a collector-only estimate cannot establish whole-application suitability. Free-tier eligibility is scoped to the billing account and supported regions, and does not make every associated resource free.

## Retention and historical analysis

The 30-day example above is a sizing scenario only. Phase 5 targets analysis across multiple months; retention must cover the chosen analytical window and its replay/correction needs before collection starts. Approve raw, normalized and aggregate retention separately, including source rights, capture manifests, static timetable versions and gaps.

A shorter raw window can support longer analytical history only if the required longer-lived records are actually produced, validated and retained, and the loss of older raw replay is explicitly accepted. Do not assume deleted raw inputs can be regenerated or that aggregation preserves every future analysis. Shared payload objects require reference-aware retention; compression savings must be measured. A-03 and A-06 must resolve this with the historical requirements before CLOUD-01 enables a deletion policy.

## Controls and decision before provisioning

Approve the host, region, runtime/deployment identities, retention and operating limits before CLOUD-01 provisioning. Configure alert and shutdown thresholds privately; public runbooks describe their behavior and the resulting capture-gap handling. Alerts alone do not stop spending. Verify any service-specific spend-cap support and use enforceable request/retry limits, response size/time limits, bounded logs, storage monitoring and a documented stop procedure.

Use a dedicated runtime service account with narrowly scoped bucket/secret permissions, separate deployment identity and no committed credential files. Test create-only raw writes, manifest reconciliation and deployment lease/fencing against the proposed [capture contract](capture-event-contract.md). One nominal instance does not prevent overlap during rollout or recovery.

Source-use/retention approval and SRC-02 live-access proof remain separate gates. The fixture-to-area work continues in parallel.

## Provider references

- [GCP free-tier eligibility and regional limits](https://docs.cloud.google.com/free/docs/free-cloud-features)
- [Compute Engine pricing](https://cloud.google.com/products/compute/pricing/general-purpose), [disk pricing](https://cloud.google.com/compute/disks-image-pricing) and [network pricing](https://cloud.google.com/vpc/network-pricing)
- [Cloud Run worker pools](https://docs.cloud.google.com/run/docs/deploy-worker-pools) and [pricing](https://cloud.google.com/run/pricing#worker-pools)
- [GCS storage and operation pricing](https://cloud.google.com/storage/pricing)
- [Hetzner shared cloud plans](https://www.hetzner.com/cloud/cost-optimized/) and [billing behavior](https://docs.hetzner.com/cloud/billing/faq/)
- [GCP budget controls](https://docs.cloud.google.com/billing/docs/how-to/budgets)

Recheck provider terms, regional availability and prices before deployment. Public documentation records the technical trade-offs and workload assumptions; project-specific financial figures stay outside the repository.

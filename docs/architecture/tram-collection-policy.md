# SRC-02 tram collection policy

Date: 2026-10-07. Status: **Cadence accepted by the project architect on 2026-10-07: positions 60 seconds, trip updates 120 seconds, alerts 60 seconds.** Raw retention duration and final source-use/attribution acceptance remain proposed. This decision does not start live collection, delete history or provision cloud resources. It refines polling under [ADR 0015](../adr/0015-local-capture-collector.md). [Probe evidence](../evidence/src-02-transport-probe.md) remains a short sample, not a verified subscription limit.

The accepted preference prioritizes useful retained history over minimum live latency. The accepted MAP-02 design uses constant-speed interpolation between two eligible observations on the same verified path; increasing polling frequency is not required to draw intermediate frames. Interpolation cannot recover unobserved changes or advance beyond the latest eligible observation.

## Options

Intervals are positions / trip updates / alerts, in seconds. One subscription-wide dispatcher includes every request and retry; no concurrent probe or second collector may spend the same budget.

| Cadence option | Intervals | Requests/day | Average requests/minute | Unused share of 20/min comparison floor | Raw MB/day | Raw GB/14 days (illustration only) |
| --- | --- | --- | --- | --- | --- | --- |
| Higher sampling | 30 / 60 / 60 | 5,760 | 4 | 80% | 164.35–169.66 | 2.30–2.38 |
| Lowest request count | 60 / 120 / 120 | 2,880 | 2 | 90% | 82.18–84.83 | 1.15–1.19 |
| **Accepted cadence** | **60 / 120 / 60** | **3,600** | **2.5** | **87.5%** | **82.86–86.36** | **1.16–1.21** |

The accepted cadence keeps alerts at one minute while roughly halving payload storage relative to higher sampling. Its additional raw bytes over 60/120/120 are small because alerts were small in the sample. Fewer positions/updates retain less temporal detail; future interpolation does not restore missing observations. The 14-day column compares equal horizons and does not select retention.

Estimates use decimal MB/GB and the observed minimum/maximum payload bytes: positions 13,868–14,229, updates 85,444–87,229, alerts 955–2,130. Formula per day: `sum(86400 / interval * bytes_per_response)`. They exclude retries, manifests, sequence indexes, sessions, filesystem allocation, pinned backlog, static archives and backups. These are samples, not bounds on a full day's feed size. The accepted cadence creates 3,600 captures/day (50,400 in an illustrative 14 days); many small metadata files may materially increase disk use. Compression and deduplication are unimplemented and are not credited to these estimates.

Reproduce the table without network access:

```python
sizes = [(13868, 14229), (85444, 87229), (955, 2130)]
for intervals, days in [((30, 60, 60), 14), ((60, 120, 120), 14), ((60, 120, 60), 14)]:
    daily = [sum(86400 // s * size[i] for s, size in zip(intervals, sizes)) for i in (0, 1)]
    print(intervals, days, [round(n / 1_000_000, 2) for n in daily])
    print([round(n * days / 1_000_000_000, 2) for n in daily])
```

## Scheduling and failure behavior

For the accepted cadence, healthy slots in each two-minute cycle are positions at seconds 0 and 60, updates at 15, and alerts at 30 and 90. This is five requests per two minutes; individual minutes need not contain the average 2.5 requests. The dispatcher serializes requests, spaces starts by at least 15 seconds and enforces at most four starts in any half-open rolling 60-second window, including failures/retries. Slow responses, backoff or outages move work later: skip missed slots, never burst to catch up. Honor longer Retry-After deadlines across restart. Retain the existing 60-second live startup delay and finite CLI bounds until continuous operation has its own reviewed implementation.

The current collector rotates all three feeds equally and retries the failed feed. It cannot implement the differentiated schedule above unchanged. A scheduler change must test per-feed fairness, retry accounting, restart/backoff and no catch-up bursts. Repeated failure of one source must remain visible without quietly starving the other two. No request-rate increase is part of this proposal.

The [official collection](https://opendata.transport.vic.gov.au/dataset/gtfs-realtime) states 24 calls/60 seconds and 60-second tram refresh. The [positions OpenAPI](https://opendata.transport.vic.gov.au/dataset/2d9a7228-5b81-40d3-8075-ae7a3da42198/resource/a42c2344-38da-4c52-805b-36004dea3cac/download/gtfsr_yarra_trams_vehicle_positions.openapi.json) states 20–27 calls/minute and a 30-second cache. Both were checked on 2026-10-07. The 20/min floor is only a conservative comparison, not confirmation of account/endpoint scope or permission to use the remaining capacity. Resolve subscription scope before unattended operation; do not stress-test the limit. The bounded probe's successful requests do not establish a quota guarantee. Polling every 30 seconds does not mean a position is 30 seconds old.

## Retention and downstream history

Raw duration is **not yet selected**. The proposal remains **14 days of complete raw responses** locally, measured from successful receipt, retaining exact bytes and provenance. Normalize selected-area history separately for later multi-month analysis; a short raw window is not the analytical-history window. Long-term normalized retention/grain remains A-07/HIST-01.

Never expire an unnormalized capture, unresolved verification finding, or raw evidence backing an unconfirmed upload. Preserve pending object records until confirmation under ADR 0015; HTTP 412 alone is not confirmation. If the uploader is not ready, these pins can make every capture ineligible for deletion. Report oldest capture, pinned bytes, free bytes and gaps; stop safely before the existing reserve is crossed. Do not overwrite or manually delete history to keep collection running.

The v2 store currently verifies every allocated sequence and immutable capture; deleting payloads/directories would violate that contract. Retention therefore requires a separately reviewed expiry/tombstone design, corresponding verifier/cursor behavior and crash tests. Until implemented, use finite capture runs and capacity checks; accepting a duration does not turn on a cleanup script or alter persisted format. Keep static release hashes and the corresponding lookup material while retained normalized data depends on them.

## Source use and attribution

The official [GTFS Realtime](https://opendata.transport.vic.gov.au/dataset/gtfs-realtime) and [GTFS Schedule](https://opendata.transport.vic.gov.au/dataset/gtfs-schedule) catalogues identify the Department of Transport and Planning and CC BY 4.0. The [licence](https://creativecommons.org/licenses/by/4.0/) permits sharing/adaptation subject to credit, licence links, preserved notices and change identification; do not imply endorsement. Dataset licensing does not resolve API subscription conditions or quota scope.

Proposed visible credit:

> Transport data: Department of Transport and Planning, Victoria — GTFS Realtime and GTFS Schedule, CC BY 4.0. Filtered and transformed by UrbanPulse; not an official transport service.

Link dataset names and CC BY 4.0 in the map attribution/data-source panel. Describe shape clipping, selected-area normalization and timestamp handling in evidence/export metadata. Carry source URL, release/capture identity, original notices, licence URL and transformation version in manifests and published derived exports. Keep Observed, Interpolated and Synthetic labels separate; synthetic vehicle movement over official geometry must never look like a live provider observation. Keep raw provider payloads and credentials out of the public repository.

## Architect selection and activation gates

Cadence is selected above. The architect must still select the raw retention duration and accept/amend the source-use and attribution rules. Record those decisions explicitly; the cadence decision does not implicitly approve the illustrative 14-day window or start collection.

After selection: implement/test the schedule, review retention persistence separately, verify dedicated-host requirements, monitoring and free-space/backlog behavior, confirm subscription scope, then authorize a bounded live run with explicit duration/request limits. That run must record observed byte totals, cadence, errors and gaps. Live projection freshness, correction/disappearance semantics, public live UI and unattended operation remain separate decisions; this policy does not select them.
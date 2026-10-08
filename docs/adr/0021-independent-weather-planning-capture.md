# ADR 0021: Lightweight Weather and DAM capture

Date: 2026-10-08

Status: **Timer-based approach and cadence accepted by the project architect; format and operating rules below proposed for review before implementation.** Supersedes the earlier shared-journal implementation proposal. No source job or timer is deployed by this document.

## Scope

Run bounded jobs based on `scripts/source_probe.py` through separate **systemd timers**: Weather every **15 minutes**, DAM **daily**, for Southbank and Melbourne CBD. Each source has its own encrypted-volume directory, service and timer. Do not extend the Tram store, generalize its journal, change its code/service/loop, or mount its DTP key. Provider requests need no API key. Timers do not queue overlapping executions or burst through missed schedules after reboot; the volume must be manually unlocked and its mount/UUID checked first.

Keep the current collector image dependency set where practical; do not add an always-running daemon, database or general workflow engine. This is private collection only. Open-Meteo serving eligibility and both sources' retention durations remain pending; the architect permits collection while those decisions are open. No public serving, automatic expiry, normalization or upload is enabled by this slice.

## Files and completion

Each source directory uses this small versioned layout:

```text
attempts/<uuid>/attempt.json         immutable start, source, selected areas, code version
attempts/<uuid>/responses/<n>.json  immutable request/receipt metadata and raw object hash
attempts/<uuid>/manifest.json       immutable terminal result: complete or incomplete
objects/<sha256>.bin                immutable raw response bytes, reused by exact hash
versions/<content-sha256>.json      DAM complete selected-content version only
```

Request metadata includes endpoint/parameters, HTTP status, requested/received times, byte count and SHA-256; secrets are never included. Write to a temporary file, fsync, then publish create-only and fsync the directory. Validate an existing content-addressed object before reuse; never overwrite it. Only a complete manifest referencing durable, hash-checked responses constitutes success. A failed job publishes an incomplete manifest where storage permits; an attempt without a terminal manifest is also explicitly incomplete. Interrupted temporary files never establish success. The next timer starts a new attempt; it does not resume old pagination or repair historical records.

One Weather attempt contains the two current-reading responses, retaining effective time, units and missing values. Both must pass validation to count as complete. Modelled readings do not establish warning coverage. No provider data is represented as a station observation.

## DAM snapshot and change detection

One DAM attempt contains **metadata before → every page for both areas → metadata after**. Use stable development-key ordering, pages of 100, at most ten pages / 1,000 rows per area, **22 requests**, 2 MiB per response and 8 MiB total retained response bytes, with a 180-second overall deadline and 15-second request timeout. The deadline must cover body reads, not only checks between requests. Bounds are fail-safe limits; hitting them never means the source is complete.

Validate area labels, field types, unique development IDs, advertised totals and complete pagination. Before/after modification time, processing time and dataset count must be present and equal. Changed/missing metadata, duplicate IDs, conflicting totals, a failed/empty early page or an exceeded bound makes the whole snapshot incomplete. Preserve the bounded diagnostic responses and do not advance the last complete version or success time. Matching metadata improves consistency but cannot establish transactional provider isolation.

Hash canonical selected records sorted by area and development ID, preserving source status and point values; exclude request times and pagination order. Publish a new **data version only when this content hash changes**. An unchanged complete check writes its own manifest referencing the existing version and counts as a success. Identical raw response bytes reuse existing SHA-256 objects; different raw bytes remain retained evidence even if formatting alone changes and the semantic version stays the same. Missing rows are only absent from that complete snapshot, not inferred cancelled or completed.

## Shared-volume reserve order

The existing Tram byte/inode stop floors remain unchanged. Before activation, inspect those floors and configure **strictly higher floors for both new sources**, with margin for their bounded staging/publication overhead and Tram writes during a job. Record the concrete settings privately; they are not selected by this ADR.

Weather/DAM jobs share one non-blocking admission lock with each other, never with Tram. This keeps their maximum simultaneous allocation bounded to one new-source job. Before creating an attempt or making requests, require enough available bytes/inodes for that maximum job allocation **above** the new-source stop floors. Recheck before each write; stop safely if headroom disappears. Admit no new attempt on insufficient capacity. Neither job deletes evidence to free space. Set `Restart=no`; the next scheduled invocation may check capacity again but must not create a new attempt/session file while below reserve. A skipped or incomplete attempt does not refresh last success. The unchanged Tram reserve remains the final independent safety guard.

## Minimal monitoring and activation

Publish a **last-complete-success timestamp** for each source, plus an explicit never-succeeded state until one exists. Unchanged complete DAM checks refresh that timestamp; HTTP 200 alone does not. Keep Weather and DAM alert enrollment independent of each other, Tram and upload. Alert evaluation must detect both an old reported timestamp and an absent/stopped metric stream; a previous successful timestamp must not mask a dead timer. Thresholds allow each source's cadence and job deadline and are reviewed separately.

Public source fetching is keyless. Sending Cloud Monitoring metrics still needs authentication: reuse the already approved metrics identity through the existing protected telemetry path where possible; do not create a new key or broaden IAM implicitly. The provider capture job receives no DTP key. Any necessary telemetry access/service wiring is explicit in the implementation review.

Terraform metric/alert changes and actual enrollment require a **separate saved-plan approval**. Before unattended activation, verify finite jobs, encrypted mount refusal, timer non-overlap, complete/incomplete behavior, reserve refusal without file growth, source-specific metric readback and notification delivery. Do not repeat or alter accepted Tram host tests.

## Implementation acceptance

Test immutable publication/crash interruption, hash mismatch, multi-page changes/failures, unchanged versus changed DAM versions, missing values, deadline/request/byte limits, concurrent timer admission and reserve ordering. Keep private source/host data out of public fixtures. Update the source register and runbook with actual deployment evidence only after activation.

References: [bounded source probe](../evidence/src-02-weather-planning-probe.md), [source register](../source-register.md), [host policy](0015-local-capture-collector.md), [monitoring boundary](0019-capture-infrastructure-and-monitoring.md).

# ADR 0021: Cloud Weather and DAM capture

Date: 2026-10-08

Status: **Cloud Run Job + Cloud Scheduler, cadence, cloud raw retention permission and dedicated keyless prefix-write identities accepted by the project architect on 2026-10-08.** Replaces the systemd timer/shared-journal proposals. Detailed implementation and alert acceptance below remain review gates; no resources are deployed by this document.

## Scope and ownership

Use independent bounded Cloud Run Jobs based on `scripts/source_probe.py`, invoked by Cloud Scheduler: Weather every **15 minutes**, DAM **daily**, for Southbank and Melbourne CBD. Use UTC schedules and record provider effective time separately from receipt time. Scheduler only starts an execution; successful dispatch does not mean successful capture. Bound task count, retries, memory, requests and execution time. Duplicate/overlapping dispatches must remain safe: each execution/task attempt has a fresh capture identity, immutable objects and no mutable latest pointer. Downstream processing deduplicates input/semantic versions. [Scheduling jobs](https://docs.cloud.google.com/run/docs/execute/jobs-on-schedule), [at-least-once delivery](https://docs.cloud.google.com/scheduler/docs/overview).

Weather/DAM raw may be retained in GCS with source attribution and CC BY 4.0 notices. Retention durations and automated expiry remain undecided; do not install lifecycle deletion or a bucket retention lock implicitly. Open-Meteo API eligibility remains a distinct source-use check, including before public serving; CC BY data licensing does not override the API's non-commercial access terms. The architect authorizes private cloud collection while remaining serving/expiry decisions are open. [Open-Meteo terms](https://open-meteo.com/en/terms), [DAM catalogue](https://data.melbourne.vic.gov.au/explore/dataset/development-activity-monitor/).

Tram raw remains local under its existing policy. Do not change its store, journal, loop, host service, DTP key, reserve or upload identity. No home-host jobs or shared disk admission lock are added. Dagster/warehouse/serving and the live map are later slices, not implicit additions to this capture PR.

## GCS layout and immutable completion

Use separate source prefixes, outside the existing normalized Tram landing namespace:

```text
raw/weather/date=YYYY-MM-DD/<capture-id>/
raw/dam/date=YYYY-MM-DD/<capture-id>/
  attempt.json          immutable identity, source, scope, image/code version and start
  incomplete.json       immutable initial pending marker
  responses/<n>.bin     immutable bounded provider response bytes
  receipts/<n>.json     immutable request/status/times/length/SHA-256
  manifest.json         immutable terminal complete/incomplete result
```

The date is the UTC attempt-start date, not the provider's observation date. Write the attempt and pending marker successfully before provider requests. A **complete terminal manifest**, published last and referencing every acknowledged response and receipt, is the only success criterion. The initial marker remains immutable: complete manifest takes precedence; explicit incomplete manifest or no terminal manifest means incomplete. A crash even before the marker is written is still an unsuccessful attempt. No rename, overwrite, marker deletion or fsync-on-local-disk protocol is assumed for GCS.

Create objects with `ifGenerationMatch=0`, bounded single-request uploads and service-validated transfer checksums. Retain SHA-256 in receipts/manifests and acknowledged object generations for later consumers to verify. Do not trust an uploader-supplied SHA alone as upload confirmation. Lost acknowledgement or `412` is **not verified success** under write-only access: fail the attempt without reading/overwriting the object. A new execution uses a fresh identity. Partial objects/attempts stay outside successful processing; later authorized readers may reconcile them. [Request preconditions](https://docs.cloud.google.com/storage/docs/request-preconditions), [transfer validation](https://docs.cloud.google.com/storage/docs/data-validation).

## Snapshot rules

Weather: capture both current-reading responses; validate requested units, values and effective times, preserving nulls and model provenance. Both must pass for a complete check. This is model output, not station observation or hazard-warning coverage.

DAM: one logical capture is **metadata before → every page for both areas → metadata after**. Stable development-key order; 100 rows/page, at most ten pages and 1,000 rows/area, 22 requests, 2 MiB/response and 8 MiB total source-response bytes; 180-second fetch deadline covering streamed bodies, 15-second request timeout. The job deadline additionally allows bounded uploads and shutdown. Validate unique IDs, area labels, field types, stable totals and exhaustive pagination. Before/after modification time, processing time and dataset count must be present and equal. Changed/missing metadata, duplicates, conflicting totals, failed/empty early pages or any bound exceeded makes the snapshot incomplete. Retain bounded diagnostic bytes; do not report complete success. Equal metadata does not prove transactional provider isolation.

Store a canonical selected-content hash in each complete DAM manifest, sorting by area/development ID and excluding fetch times/pagination order. **Capture writers cannot read previous versions.** Therefore daily raw captures remain immutable evidence; the later authorized processing layer compares this hash and publishes a new logical DAM data version only on change. An unchanged complete daily capture still refreshes last success. This distinguishes raw capture from change-only data-version publication; do not claim cross-run deduplication in the write-only job or silently add read access. Absence from a complete snapshot is not evidence of cancellation/completion.

## Identities and storage access

Give each source Job a dedicated runtime SA through Cloud Run service identity/ADC, with no SA key. Grant only `storage.objects.create` through a custom storage role, conditionally scoped to that source's object prefix, for example `resource.name.startsWith('projects/_/buckets/BUCKET/objects/raw/weather/')`. Use a trailing slash and uniform bucket-level access. No object get/list/delete/overwrite, bucket administration, Tram prefix or other-source write access. Effective IAM must include inherited grants in the review. Scheduler uses a separate invoker identity restricted to the corresponding job; runtime cannot grant IAM or invoke other jobs. [Prefix conditions and their limits](https://docs.cloud.google.com/storage/docs/access-control/iam).

The saved infrastructure plan chooses the raw bucket and demonstrates isolation from existing home-uploader grants; a different prefix alone cannot cancel that identity's existing bucket-wide permissions. Prefer a dedicated cloud-raw bucket if reusing a bucket would expose raw through those grants. No raw upload permission is added to the home collector.

## Failure and last-success alerts

Use platform Job execution failures plus **last complete success** per source. Emit a structured success log only after acknowledged publication of a complete manifest, with completion timestamp and capture reference. Cloud Run collects stdout/stderr; do not add `monitoring.timeSeries.create` or Logging API permissions to the prefix-only writer implicitly. Last-success time is traceable to the log/manifest; a log-based success signal can support freshness alerting. Do not claim a log-based counter is a custom timestamp gauge. Each source has independent enrollment/alerts, separate from Tram/upload. HTTP 200, Scheduler dispatch and an incomplete capture never refresh success.

**DAM window gate (official limits checked 2026-10-08):** ordinary metric-absence conditions allow at most **23.5 hours**, so they cannot safely monitor a daily job plus grace. Standard metric alignment also has an approximately one-day lookback limit reduced by ingestion delay. PromQL-based policies support longer lookbacks; windows over 25 hours and up to eight days require evaluation intervals of at least five minutes. A **26-hour success lookback** is a candidate, not an approved or tested threshold. Retest duration is distinct from lookback. [Metric absence limit](https://docs.cloud.google.com/monitoring/alerts/metric-absence), [alignment behavior](https://docs.cloud.google.com/monitoring/alerts/concepts-indepth), [PromQL limits](https://docs.cloud.google.com/monitoring/alerts/using-promql).

Before selecting/enrolling an alert, validate the actual log-derived metric and query against sparse daily samples, delayed ingestion, zero-filled samples, failed executions, disabled Scheduler and a source that has never succeeded. Ensure missing series triggers after an explicit enrollment grace, rather than evaluating to an empty/non-alerting result. Demonstrate successful daily jobs do not alert, missed daily capture does, and recovery clears the incident. If the query cannot meet these cases, return an alternative for review; do not add a resident monitor or wider runtime IAM silently. Weather gets a separate window appropriate to its 15-minute cadence. Notification destinations and exact thresholds belong to the saved plan review.

## Delivery gates

Implement/tests first, then review Terraform separately; no apply is authorized by this ADR. Verify source parsing, full/incomplete pagination, immutable objects, crash/lost-ack/412 behavior, duplicate dispatch and bounded resource failure. Test prefix writes allowed and get/list/delete/overwrite/cross-prefix writes denied with the real identities. Run finite cloud captures, verify manifests/checksums and execution outcome, then validate alerts/notifications before enabling unattended schedules. Keep the current Tram collection and accepted host tests untouched.

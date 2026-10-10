# Daily GTFS Schedule archive

Status: **Daily check, change-only archive and dedicated keyless create+get identity accepted by the project architect on 2026-10-08; archive scope and export dependency accepted on 2026-10-08; implementation and cloud-plan validation remain separate.** Runs alongside Phase 1 schema development and must be deployed and accepted before the Phase 1a export. It does not alter the home realtime collector or the approved Weather/DAM prefix-write boundary.

Use a separate bounded Cloud Run Job and Cloud Scheduler daily. Download the official static release over HTTPS without a DTP realtime key. Record retrieval time, source URL, provider Last-Modified/ETag where supplied, outer ZIP SHA-256 and selected tram member SHA-256. Last-Modified and ETag are source hints, not content checksums. Store an unchanged-check receipt even when no new archive is published.

Archive only the exact **tram member ZIP** (`3/google_transit.zip`), addressed by its byte SHA-256. Keep the outer statewide ZIP hash in each retrieval manifest, but do not upload the outer ZIP or other modes. Tram normalization/static joins use the tram member hash: a bus-only outer release change adds a check receipt with the new outer hash, not a duplicate tram archive. Preserve trips, stop_times, stops, routes, calendar, calendar_dates, shapes and other member content together, not only geometries. Record coverage dates and absence of required files. Do not relabel a newly downloaded release as the schedule that was available at an older capture time; pin the actual chosen release and expose missing/ambiguous history.

The full release still needs bounded temporary download/validation to extract the tram member, even though only that member is archived. The full release is much larger than the Weather/DAM responses. Use independent reviewed compressed/download, expanded-member, deadline and memory limits based on the catalogue and a finite measurement. Validate ZIP entries, duplicate/traversal paths and decompression bounds without extraction outside the job workspace. Do not reuse the 8 MiB Weather/DAM bound or silently change the home upload-record limit. Cloud download/archive resources are separately planned.

## First archive and export dependency

Seed the first archive from the original locally retained SRC-02/MAP-02 timetable, not a fresh download presented as historical input. Rehash the retained outer ZIP and member and compare with both evidence records before publication:

| Input | Expected SHA-256 |
| --- | --- |
| Original statewide ZIP (provenance only) | `7eb6562c7b19f5685740f3da9f95440bd964681b76c9dc5854f4cb4d08ae393d` |
| Exact tram member ZIP (archived bytes) | `df140ec0fd415d9ce3bd45ff3a47dbb8a65668168fe20a5fd442dc5fa0a62536` |

These are the same release used by [SRC-02](../evidence/src-02-transport-probe.md) and [MAP-02](../evidence/map-02-trip-foundation.md), not two separate releases. Preserve every original download receipt/source reference. Archive metadata separates `original_downloaded_at`, `archived_at`, provider `last_modified`, source URL, outer ZIP hash and tram-member hash. Reusing the archive in a later probe does not reset its download time. The source download record currently retains Last-Modified `2026-10-04T01:31:37Z`, URL, bytes and hashes, but **does not contain an original download timestamp**. Recover that timestamp from original operator/download evidence if available; never substitute file modification time, Last-Modified, probe time or upload time. If it cannot be recovered, retain null plus `download_time_unknown` and the evidence reference; expose that limitation in the export's static provenance instead of claiming exact historical availability.

Deployment order: review/apply the separate Terraform plan, seed and checksum-confirm the retained tram member under the dedicated archive identity, deploy the daily job/Scheduler, verify changed/unchanged and failed-check behavior plus alert enrollment, then permit Phase 1a export. The seed uses the approved keyless archive identity and its static prefix, not the home uploader's landing grant or a new key. A historical file can be seeded independently of a new daily check; both retain their actual retrieval provenance. Use the [archive Job runbook](../runbooks/gtfs-schedule-archive.md) for offline inspection and immutable publication. Seed and deployment acceptance remain separate gates.

Keep the complete tram member, including agency, timetable/calendar, stops, routes and shapes. Inspect source feed/calendar applicability for the exported service dates; unsupported/ambiguous dates remain unresolved and retain raw. The archive is not limited to Southbank/CBD geometry. A daily failed check cannot advance last-success or overwrite the previous known member.

## Change detection and least privilege

A strict create-only writer cannot verify a pre-existing hash object after a lost acknowledgement/412; it cannot honestly declare an unchanged archive successfully confirmed. The architect selected A on 2026-10-08:

| Option | Storage permission | Consequence |
| --- | --- | --- |
| A (accepted for this distinct job) | Dedicated SA: create plus get on **only** the static archive prefix; no list/delete/overwrite | Direct known-hash metadata/checksum verification supports confirmed change-only archive without a separate state service |
| B (not selected) | Dedicated SA: create only | Retain per-attempt evidence and let an authorized later reader reconcile/deduplicate; change-only confirmed archival is not complete within the job |

Option A's get can read content as well as metadata; the architect accepted that exposure, and a separate Terraform plan still requires approval. It does not broaden Weather/DAM writers or the home collector. Neither option is permission to store SA keys. Bucket/raw-prefix placement must preserve existing identity isolation.

Write manifests/create-only objects, verify acknowledged size/service checksum/generation and never treat a conflict as success without evidence. Job failure and a last-success signal are separately enrolled; the same daily-window validation required by [ADR 0021](../adr/0021-independent-weather-planning-capture.md#failure-and-last-success-alerts) applies. No scheduled job or IAM is deployed by this document.

Source: [DTP GTFS Schedule](https://opendata.transport.vic.gov.au/dataset/gtfs-schedule), CC BY 4.0; existing access and size evidence is in the [source register](../source-register.md#tram-track-geometry-map-02).

## Implementation and operational evidence

The bounded Job is implemented in `workers/schedule_archive`, with independent source validation and GCS adapters. See the [runbook](../runbooks/gtfs-schedule-archive.md) for limits and immutable layout, and [verification evidence](../evidence/gtfs-schedule-archive.md). Current progress is maintained in the [delivery plan](../delivery-plan.md); deployment is not implied by the offline checks.

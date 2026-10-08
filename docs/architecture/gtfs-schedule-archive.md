# Daily GTFS Schedule archive

Status: **Daily check, change-only archive and dedicated keyless create+get identity accepted by the project architect on 2026-10-08; execution details proposed for review.** Runs alongside the Phase 1 Tram slice. It does not alter the home realtime collector or the approved Weather/DAM prefix-write boundary.

Use a separate bounded Cloud Run Job and Cloud Scheduler daily. Download the official static release over HTTPS without a DTP realtime key. Record retrieval time, source URL, provider Last-Modified/ETag where supplied, outer ZIP SHA-256 and selected tram member SHA-256. Last-Modified and ETag are source hints, not content checksums. Store an unchanged-check receipt even when no new archive is published.

Archive the source ZIP by its exact byte hash so a genuinely changed full release is retained; identify tram normalization/static joins by the **tram member hash**, so unrelated bus changes do not invalidate tram shapes or analytics. Preserve trips, stop_times, stops, routes, calendar, calendar_dates, shapes and other member content together, not only geometries. Record coverage dates and absence of required files. Do not relabel a newly downloaded release as the schedule that was available at an older capture time; pin the actual chosen release and expose missing/ambiguous history.

The full release is much larger than the Weather/DAM responses. Use independent reviewed compressed/download, expanded-member, deadline and memory limits based on the catalogue and a finite measurement. Validate ZIP entries, duplicate/traversal paths and decompression bounds without extraction outside the job workspace. Do not reuse the 8 MiB Weather/DAM bound or silently change the home upload-record limit. Cloud download/archive resources are separately planned.

## Change detection and least privilege

A strict create-only writer cannot verify a pre-existing hash object after a lost acknowledgement/412; it cannot honestly declare an unchanged archive successfully confirmed. The architect selected A on 2026-10-08:

| Option | Storage permission | Consequence |
| --- | --- | --- |
| A (accepted for this distinct job) | Dedicated SA: create plus get on **only** the static archive prefix; no list/delete/overwrite | Direct known-hash metadata/checksum verification supports confirmed change-only archive without a separate state service |
| B (not selected) | Dedicated SA: create only | Retain per-attempt evidence and let an authorized later reader reconcile/deduplicate; change-only confirmed archival is not complete within the job |

Option A's get can read content as well as metadata; the architect accepted that exposure, and a separate Terraform plan still requires approval. It does not broaden Weather/DAM writers or the home collector. Neither option is permission to store SA keys. Bucket/raw-prefix placement must preserve existing identity isolation.

Write manifests/create-only objects, verify acknowledged size/service checksum/generation and never treat a conflict as success without evidence. Job failure and a last-success signal are separately enrolled; the same daily-window validation required by [ADR 0021](../adr/0021-independent-weather-planning-capture.md#failure-and-last-success-alerts) applies. No scheduled job or IAM is deployed by this proposal.

Source: [DTP GTFS Schedule](https://opendata.transport.vic.gov.au/dataset/gtfs-schedule), CC BY 4.0; existing access and size evidence is in the [source register](../source-register.md#tram-track-geometry-map-02).

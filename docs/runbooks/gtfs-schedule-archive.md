# GTFS Schedule archive Job

Implements the [accepted archive design](../architecture/gtfs-schedule-archive.md). Progress lives in the [delivery plan](../delivery-plan.md). This Job archives **static timetables**, never realtime raw or credentials. Use the existing API runtime image with a separate Cloud Run Job command; it does not start FastAPI, connect to SQL or change the home collector.

## Inspect the retained seed offline

Keep the original statewide ZIP read-only. Prepare a small provenance JSON outside Git with these fields:

```json
{
  "source_url": "https://opendata.transport.vic.gov.au/dataset/3f4e292e-7f8a-4ffe-831f-1953be0fe448/resource/fb152201-859f-4882-9206-b768060b50ad/download/gtfs.zip",
  "outer_sha256": "7eb6562c7b19f5685740f3da9f95440bd964681b76c9dc5854f4cb4d08ae393d",
  "tram_sha256": "df140ec0fd415d9ce3bd45ff3a47dbb8a65668168fe20a5fd442dc5fa0a62536",
  "original_downloaded_at": null,
  "evidence_reference": "SRC-02 / MAP-02 retained download receipt",
  "last_modified": "Sun, 04 Oct 2026 01:31:37 GMT",
  "etag": null
}
```

`original_downloaded_at: null` preserves the missing historical timestamp; the inspector does not infer it from file metadata or provider Last-Modified. Copy actual hints from the retained receipt where available. Both expected hashes are mandatory and compared with bytes before publication. A different retained release needs its own original provenance, not edited expected values merely to pass a mismatch.

Run with a new output directory, real paths and the checked-out source commit (append `-dirty` for uncommitted work):

```text
uv run --locked --no-default-groups python -m workers.schedule_archive.main inspect --source-zip /sources/gtfs.zip --provenance /sources/provenance.json --output /exports/static-inspection --code-version SOURCE_COMMIT
```

This mode does not authenticate or make network requests. The successful output is `report.json`; an interrupted output can leave `report.incomplete`. Existing output directories are refused. Inspection checks ZIP integrity and inventories every tram member, including calendar date ranges; it is not a full GTFS semantic validator or proof that every trip runs on a given service date.

## Immutable cloud publication

The separately reviewed deployment provides the dedicated archive identity and prefix-scoped create+get permissions. Runtime uses the metadata service identity directly, rejects an unexpected SA email before storage calls, and does not load a key file or developer ADC. Supply the full image source commit and pin its image digest in the deployment record.

```text
/app/.venv/bin/python -m workers.schedule_archive.main check --bucket APPROVED_BUCKET --expected-service-account ARCHIVE_SA_EMAIL --code-version SOURCE_COMMIT
```

`check` makes one bounded download from the fixed official HTTPS URL, with no redirects or automatic source retries. A historical `seed` adds `--source-zip` and `--provenance` for retained read-only inputs. The accepted local path adds `--seed-user-account` for short-lived impersonation of the explicit archive SA; it is forbidden for `check` and `inspect`. Follow the [deployment and temporary-grant runbook](gtfs-archive-deployment.md). The statewide ZIP stays local; no home-uploader permission is added.

```text
static/gtfs-tram/
  objects/sha256=<tram-member-sha256>/tram.zip
  checks/date=<UTC-start-date>/<fresh-check-id>/
    attempt.json
    incomplete.json
    manifest.json
```

Attempt and pending marker must be acknowledged before acquisition. Only an acknowledged `manifest.json` with `status: complete`, provenance, inventory and the confirmed archive generation establishes success. Pending markers remain; a complete manifest takes precedence. Incomplete or absent manifests never refresh success. Failure after archive creation can leave an unreferenced archive; a later check safely confirms it. There is no mutable latest pointer or object listing.

Objects use a single media request with `ifGenerationMatch=0` and an MD5 transfer checksum. Before uploading a known hash, read only its metadata. Existing objects, concurrent creates (412), server errors and lost upload acknowledgements are confirmed using GCS's own `md5Hash`, size, object name/bucket and generation. Record that exact generation; do not download contents or trust custom SHA metadata as proof. Mismatches fail without overwrite/delete. An unchanged tram member creates a new check manifest but no second ZIP, including when only another mode changes the outer statewide hash. Concurrent attempts have separate check IDs and reconcile the shared archive.

A complete daily check emits one structured `gtfs_archive_success` result with `completed_at`, code version and manifest generation. Historical seeds emit `gtfs_archive_seeded`, and inspections emit `gtfs_archive_inspection`; exclude both from current daily-success alerting. Exit 2, runner deadline/cancellation or a missing completion log is not success. Seed success cannot hide a broken daily download. Logs contain no token or provider error body.

## Bounds and deployment gates

| Limit | Value |
| --- | --- |
| Statewide compressed download | 512 MiB |
| Exact tram ZIP / single archive upload | 128 MiB |
| Expanded tram member / sum of all members | 512 MiB / 1 GiB |
| Entries / central-directory bytes, per ZIP | 256 / 1 MiB |
| Calendar file / calendar rows per file | 8 MiB / 100,000 |
| GCS metadata response | 64 KiB |
| Network inactivity timeout / runner deadline | 30 seconds / at most 540 seconds |

Bytes are streamed; expanded GTFS files are hashed without extracting them to disk. Reject traversal, duplicate paths, symlinks, encrypted/unsupported compression, ZIP64/multidisk or oversized indexes before processing. The parent supervises the complete operation, including authentication, stalled network and uploads. Forced interruption may leave pending evidence; restart as a fresh attempt. Temporary files belong only to the execution workspace.

Cloud Run's writable filesystem consumes memory: budget for the outer ZIP plus tram ZIP and runtime, rather than relying only on streaming heap usage. Image startup and shutdown need additional task-time headroom beyond the runner deadline. The Terraform plan must separately review memory, task timeout, one task, bounded retries, runtime identity, storage isolation, daily Scheduler, and failed-execution / last-success alert enrollment. Use the [ADR 0021 daily Monitoring-window gate](../adr/0021-independent-weather-planning-capture.md#failure-and-last-success-alerts); an ordinary metric-absence window is not sufficient for daily-plus-grace checks.

Before Phase 1a export: approve/apply that saved plan, seed the retained release, confirm cloud checksums/generation, run changed/unchanged/failure cases and prefix denial tests, then enroll and verify alerts before enabling unattended scheduling. Local tests do not establish live IAM or GCS acceptance. No raw expiry is enabled.

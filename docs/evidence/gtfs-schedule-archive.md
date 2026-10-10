# GTFS Schedule archive verification

Verified 10 October 2026. The [runbook](../runbooks/gtfs-schedule-archive.md) documents reproduction; progress and cloud gates remain in the [delivery plan](../delivery-plan.md).

## Retained source inspection

Used the original SRC-02/MAP-02 statewide ZIP read-only, not a new download. Original download time remains null with `download_time_unknown`; the receipt's Last-Modified is not substituted. Windows and an isolated Linux runtime image produced identical source hashes and inventories:

| Item | Result |
| --- | --- |
| Statewide bytes, not uploaded | 250,188,897 |
| Statewide SHA-256 | `7eb6562c7b19f5685740f3da9f95440bd964681b76c9dc5854f4cb4d08ae393d` |
| Exact tram member bytes | 19,370,388 |
| Tram SHA-256 | `df140ec0fd415d9ce3bd45ff3a47dbb8a65668168fe20a5fd442dc5fa0a62536` |
| Tram files / expanded bytes | 11 / 249,598,939 |
| Calendar rows / exception rows | 14 / 46 |
| Calendar date range | 1 October–31 December 2026; individual service applicability not established |

The Linux check used the existing API runtime image, a read-only source mount/root filesystem, no network or credentials, an unprivileged UID, dropped capabilities, a 1 GiB container limit and a separate output mount. It completed in 4.875 seconds; the runner measured cgroup lifetime peak 183,599,104 bytes (about 175 MiB). Temporary storage held the 19 MB tram ZIP, while the statewide ZIP was read from the source mount. **This does not size the cloud download:** Cloud Run's in-memory writable filesystem must also hold the downloaded outer ZIP, and startup/network/upload headroom must be measured at deployment. Windows memory telemetry was unavailable, not zero.

Reproduction uses `inspect` with the provenance template and bounds in the runbook. Reports remain private. The execution used uncommitted code based on `be0131226b18e1ef5825daecf61c520ebc34a421` with the explicit version `be01312-dirty`; the exact implementation hashes are recorded below, rather than claiming the base commit contained this Job.

| File | SHA-256 |
| --- | --- |
| `urbanpulse/adapters/gtfs_archive.py` | `e1bd5e1b7c4f1abff67d1fa659b889ca0fce239fc452bedf65be318136164e48` |
| `urbanpulse/adapters/gtfs_archive_gcs.py` | `0d87954d63652eec59f484b25e8fe6885da29fcf601dc492dfc986efcdb9f719` |
| `urbanpulse/application/schedule_archive.py` | `2618db4dbb088763b3702439ad993b378bb71d75aa7e4480d5c9576728f8e1c9` |
| `workers/schedule_archive/main.py` | `4351ba1c17f1073702a1696cce034c671c7f4c82e6fd7c11057533bfa2b5a6b7` |

## Automated behavior checks

57 archive tests pass. They cover unchanged member bytes with a changed statewide ZIP, new versus existing archives, per-check manifests, required files/calendar metadata, CRC failure, traversal/duplicates/symlinks, compressed/expanded/index/calendar-size bounds, source errors/redirects/encoding/partial bodies, deadlines, retained-seed hash mismatch and missing original download time. GCS HTTP tests inspect requests: `ifGenerationMatch=0`, transfer MD5, metadata-only reads, generation/size/server-checksum verification, conflicts, 412, response loss, no overwrite and no list/delete. Terminal-write and interruption tests prove incomplete attempts cannot produce a successful result. Seeds emit a distinct signal from current daily success.

A no-network, read-only Linux test container passed all 82 archive and Tram-audit tests in 50.05 seconds, including the existing feed-sized full-day audit. The broader Windows run had 961 passes, 183 skips and one failure: the unchanged full-day audit exceeded its five-minute deadline. Its input/tool files are unchanged in this PR; no audit bound was relaxed. Four subsequently added archive regressions are included in the 57/82/106 targeted results.

The true CLI entry point runs a synthetic offline inspection. The archive tests plus shared runner/initialization request regressions pass together (106 tests). Ruff lint/format and strict mypy pass; the new worker is included in mypy's configured scope. The existing API Docker image builds with the actual locked runtime dependencies; no new package or separate production image is introduced.

Cloud Run execution, metadata identity readback, live GCS writes/denials, historical seed staging, Scheduler and Monitoring alerts are **not** verified by these offline/HTTP-double tests. They require the separately reviewed Terraform plan and finite cloud acceptance. No cloud resources, source permissions, collector service, realtime raw or expiry configuration were changed.

Checksum confirmation follows [GCS server-side validation](https://docs.cloud.google.com/storage/docs/data-validation): MD5 is checked by the service for these non-composite media uploads, and the adapter verifies the returned server metadata instead of trusting custom SHA metadata. SHA-256 remains the archive address and source-provenance identifier. The [official source catalogue](https://opendata.transport.vic.gov.au/dataset/gtfs-schedule) still identifies mode 3 as metropolitan tram; a daily check does not imply the provider publishes daily.


## Deployment preparation and seed authentication

The follow-up deployment checks on 10 October 2026 cover the isolated Terraform root and seed-only impersonation. Nine mocked plans pass: protected prefix-only storage, separate scheduler/runtime identities, bounded non-executing Job, default-off activation, enrollment/grace requirements, digest/source identity and same-project notification validation. Reproduce with readonly init, `terraform validate` and `terraform test` in `infra/schedule-archive`; no cloud credentials/backend or apply are used by these tests.

Archive and authentication regressions pass on Windows (73 tests) and an isolated no-network, read-only, unprivileged Linux container (73 tests, 6.14 seconds). Windows archive/auth plus shared observation/initialization-request regressions pass together (106 tests). Tests reject impersonation for check/inspect, invalid user or target identities, auth timeout/error output disclosure and metadata identity mismatch; a successful local seed requests the explicit target and short token lifetime. Ruff lint/format and strict mypy (92 source files) pass.

These tests use authentication/storage doubles. At that pre-apply stage, no actual temporary grant, local impersonated upload, new image publication, cloud plan/apply, scheduler dispatch or daily Monitoring query had been executed by the follow-up. The subsequent initialization and readbacks are recorded below. Real acceptance follows the [deployment runbook](../runbooks/gtfs-archive-deployment.md), including the log-metric 25-hour lookback constraint and notification cases.


## Initial infrastructure apply and region correction

The separately approved initialization plan created 11 resources on 10 October 2026. Cloud Scheduler then rejected Melbourne as unsupported; the run ended with a partial apply, not deployment completion. The saved state was backed up before and after. Direct API readbacks confirm the Melbourne bucket, exact prefix-scoped archive grant, separate Job invoker, zero executions and both alerts disabled. This establishes configuration readback, not live data-access denial tests or collection acceptance.

The live Scheduler ListLocations response and [official catalogue](https://docs.cloud.google.com/scheduler/docs/locations) list Sydney as the available Australian region. The correction keeps storage and the target Job in Melbourne and proposes only the paused Scheduler in Sydney. The replacement plan contains one creation, zero updates and zero deletions; it awaits separate approval. All nine mocked deployment tests pass, including the Sydney scheduler/Melbourne target invariant. Historical seed and unattended capture have not started.

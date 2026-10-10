# Deploy the static GTFS archive

Implements [ADR 0023](../adr/0023-gtfs-archive-deployment.md). The [worker runbook](gtfs-schedule-archive.md) defines source validation, layout and offline inspection. This root does not change home Tram capture, raw expiry or existing serving resources.

## Prepare a reviewable plan

1. Check [Cloud Scheduler locations](https://docs.cloud.google.com/scheduler/docs/locations) and the project ListLocations response. Melbourne is not supported: the correction proposes Scheduler in Sydney (`australia-southeast1`), with the target Job and bucket retained in Melbourne. Review this region split in the saved plan before creating Scheduler. Confirm the existing Run, Storage, IAM Credentials, Logging and Monitoring APIs and deployer permissions. This root enables only Scheduler, with `disable_on_destroy=false`; do not take ownership of APIs managed by other roots. Confirm the Cloud Scheduler service agent has its provider-managed role before dispatch acceptance. Do not grant it archive data access.
2. Build/publish the tested API runtime image using the existing protected image workflow. Read back its source label and immutable manifest digest. Do not use a mutable tag or an image predating this worker.
3. Copy `infra/schedule-archive/terraform.tfvars.example` to ignored `terraform.tfvars`, supply the reviewed project, **new bucket**, image digest and commit. Keep schedule/alerts disabled. Proposed task resources: 1 CPU, 2 GiB, 900 seconds including startup; runner 540 seconds. The outer ZIP can occupy 512 MiB and tram ZIP 128 MiB of memory-backed storage; the offline memory measurement excludes a cloud outer download.
4. Use the accepted versioned GCS state bucket with a dedicated `schedule-archive/` prefix. Create ignored `infra/schedule-archive/backend.tf` with the actual bucket, not the collector's `capture/` or serving prefix. Back up any existing state before/after changes, verify hashes and retain the previous copy. Never migrate another root's state into this one.
5. Run readonly initialization, validation and save one plan:

```powershell
terraform -chdir=infra/schedule-archive init -input=false -lockfile=readonly
terraform -chdir=infra/schedule-archive validate
terraform -chdir=infra/schedule-archive plan "-out=archive.tfplan"
terraform -chdir=infra/schedule-archive show -no-color archive.tfplan
```

Review the exact SHA-256, resource diff, runtime and invoker principals, conditional prefix, absence of key/project-wide storage grants, paused Scheduler and disabled alerts. The root uses no Terraform secret values and grants no temporary Token Creator role. After approval, apply **that saved plan**. No execution token is set: apply does not run the Job. Read back resources and effective inherited IAM; a mock cannot demonstrate least privilege. Existing broad inherited grants must be resolved before acceptance.

## Seed the retained timetable without a key

First inspect the retained ZIP offline with original provenance and expected hashes. Prepare a private IAM review containing operator user, archive SA from Terraform output, project, absolute expiry (at most four hours), condition title, reason, current SA policy and removal procedure. Confirm only the accepted archive identity is targeted. The administrator approves this separately from infrastructure apply.

Save a private UTF-8 `seed-condition.json` with the reviewed expiry and title. A condition file avoids Windows PowerShell 5.1 removing quotation marks passed to native commands:

```json
{
  "expression": "request.time < timestamp(\"REVIEWED_UTC_EXPIRY\")",
  "title": "gtfs-retained-seed"
}
```

Example PowerShell variables contain **reviewed values**, not credentials:

```powershell
$ArchiveSa = 'ARCHIVE_SA_EMAIL'
$SeedMember = 'user:OPERATOR_EMAIL'
$SeedUser = 'OPERATOR_EMAIL'
$SeedConditionFile = 'PRIVATE_PATH/seed-condition.json'
gcloud iam service-accounts get-iam-policy $ArchiveSa --format=json
gcloud iam service-accounts add-iam-policy-binding $ArchiveSa "--member=$SeedMember" --role=roles/iam.serviceAccountTokenCreator "--condition-from-file=$SeedConditionFile"
gcloud iam service-accounts get-iam-policy $ArchiveSa --format=json
```

Run this only after the grant is read back with the exact member, role and expiry. Authenticate the named user through the normal Google CLI login flow beforehand; do not install a key, configure an access-token file or enable HTTP debug logging. The seed captures `gcloud auth print-access-token --impersonate-service-account` output internally; **do not run that token command yourself**. The worker requests a 900-second token and never falls back to uploading as the user.

```powershell
try {
    uv run --locked --no-default-groups python -m workers.schedule_archive.main seed --source-zip LOCAL_RETAINED_ZIP --provenance LOCAL_PROVENANCE_JSON --bucket APPROVED_ARCHIVE_BUCKET --expected-service-account $ArchiveSa --seed-user-account $SeedUser --code-version REVIEWED_SOURCE_COMMIT
    if ($LASTEXITCODE -ne 0) { throw 'Seed failed; preserve the attempt for investigation.' }
} finally {
    gcloud iam service-accounts remove-iam-policy-binding $ArchiveSa "--member=$SeedMember" --role=roles/iam.serviceAccountTokenCreator "--condition-from-file=$SeedConditionFile"
    if ($LASTEXITCODE -ne 0) { throw 'Temporary grant removal failed: administrator follow-up required.' }
    gcloud iam service-accounts get-iam-policy $ArchiveSa --format=json
}
```

Record manifest path/generation, checksum comparison, source hashes, unknown original timestamp where applicable, grant/removal times and readback privately. Confirm the exact temporary binding is absent and no unconditional duplicate remains. A crashed terminal does not run `finally`: remove the binding explicitly using the saved condition; its expiry remains the fallback. Removing a binding does not revoke already issued tokens; allow their 15-minute lifetime to elapse. Use Cloud Audit Logs to confirm the impersonated principal and target operations, never record tokens. Seed failure is not permission to broaden IAM or automatically retry a conflicting object.

## Finite cloud acceptance

Keep Scheduler paused. Manually execute the exact reviewed Job, record execution/image/source identity, start/end time, peak memory, exit result and acknowledged manifest. Run a second check: unchanged tram bytes must retain the same archive generation, with a new check manifest. Validate a changed tram member and an incomplete/failing source in an isolated acceptance target; never alter a retained production archive to manufacture the case.

Test with the actual archive identity: create/get within its prefix allowed; list, delete, overwrite, cross-prefix/bucket access and SQL/secret access denied. Test the invoker can invoke this Job but cannot read archives or invoke another Job. Use bounded test objects in the prefix; operators with existing separate administration may remove only designated test objects. Task timeout/OOM/cancellation must produce no complete manifest and must fail the execution. Parallelism one is not a cross-execution mutex; verify duplicate dispatch creates separate manifests and safely reconciles the content-addressed ZIP.

## Alert enrollment and schedule activation

Two independent signals are prepared: platform `run.googleapis.com/job/completed_execution_count` with `result=failed`, and a log-derived DELTA counter filtered to `status=complete`, `kind=gtfs_archive_success` and the exact project/region/Job. Seeds, inspections, HTTP success and Scheduler acceptance are excluded. The last complete timestamp remains in logs/manifests; this counter is not a timestamp gauge.

The candidate query uses the maximum **positive** success sample in 24h30m, a zero fallback for missing series, and an explicit `alert_not_before` Unix second. Zero-filled samples do not refresh success. Evaluation is every five minutes with no retest delay. Daily dispatch is 18:00 UTC, avoiding daylight-saving drift; the half-hour grace must cover runtime plus ingestion jitter. These are proposed settings for saved-plan review, not production evidence.

[Current Monitoring limits](https://docs.cloud.google.com/monitoring/alerts/using-promql) restrict user-defined log/custom metrics to 25 hours. A 26-hour lookback is not valid for this metric. Do not substitute `condition_absent` (maximum 23.5 hours) or extend the query without verification. See [log metric zero/gap behavior](https://docs.cloud.google.com/logging/docs/logs-based-metrics) and [Cloud Run metric descriptors](https://docs.cloud.google.com/monitoring/api/metrics_gcp_p_z).

Before setting `alerts_enrolled=true`, query the **actual** metric/labels using the output `last_success_query` and archive results for:

| Case | Required result |
| --- | --- |
| Single sparse positive completion within window, then zero fills | Healthy; neither silence nor zero fills count as new success |
| No positive completion for more than the window | Alert |
| No series has ever existed, grace elapsed | Alert, not empty result |
| Incomplete attempt, seed or failed execution | Does not refresh daily success; execution failure also alerts |
| Delayed ingestion near the window edge | Measured grace is sufficient; otherwise revise reviewed cadence/window |
| Paused Scheduler or removed Job | Missing-success alerts after grace; maintenance uses a reviewed snooze |
| Recovery with a newly confirmed daily manifest | Incident clears; notification received |

Validate actual DELTA-to-PromQL behavior, metric existence and sample timestamps: mocked Terraform and ordinary Prometheus cannot establish Google's backend semantics. If the query/window fails any case, keep enrollment off and return a revised design; do not add a resident monitor or widen runtime IAM. DAM requires its own source-specific acceptance.

Review a second saved plan with explicit grace, verified existing notification channels and alert enrollment; run the notification drill. Only then set `acceptance_complete=true` and `schedule_enabled=true` in another reviewed plan. Preserve UTC source timing and original archive provenance. The retained seed plus daily checks/denial tests/notifications close the static-archive gate before Phase 1a export.


## Resume a partial initialization

If apply fails after creating resources, preserve its log and immediately pull/hash a new state backup. Do not reuse the original saved plan: it describes the previous state. Read back existing resources, confirm zero executions, disabled alerts and absent/paused schedule, fix the configuration, then generate a new saved plan for separate review. Never destroy successful resources merely to restart initialization.

The first initialization on 10 October 2026 created 11 resources, then Scheduler rejected `australia-southeast2`. Live ListLocations and the official catalogue identify Sydney as the available Australian Scheduler region. The correction must add **only the paused Scheduler**; changes or replacements to the Melbourne Job, bucket, IAM or alerts require investigation before apply.

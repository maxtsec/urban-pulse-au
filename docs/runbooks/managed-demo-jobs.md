# Managed fixture Jobs

Decisions: [ADR 0010](../adr/0010-hosted-fixture-demo.md), [ADR 0012](../adr/0012-managed-demo-resource-profile.md). Progress: [delivery plan](../delivery-plan.md). [Terraform root](../../infra/demo-jobs) creates three private Cloud Run Job definitions in Melbourne, with separate state from the foundation. It reads no secret values and owns no database, API enablement or IAM resources. Creating/updating a definition does not execute it.

## Definition and prerequisites

| Job | Entrypoint and completion |
| --- | --- |
| `migrate` | Reviewed migration plus grants in one transaction; exact schema revision required |
| `import` | Pinned fixture identity checked before writes; verified history selected on success |
| `worker` | Pinned import and stable run ID; city scenario to second 360; all required deliveries complete |

All three use the same immutable API image, one task, parallelism one, zero task retries, a 600-second task timeout and a 540-second process deadline. Initial task resources are 1 vCPU and 512 MiB; record actual peak memory and duration before accepting managed execution. An OOM or timeout is failure, not permission to promote. The database-wide mutation lock, SQL role caps and refusal to reconnect after lock-session loss remain in the [runners](initialization-jobs.md). Parallelism one alone does not serialize separate executions.

The platform task timeout and the runner deadline are separate clocks. The runner starts its 540-second timer only when `supervise` is entered, after container/Python/CLI startup. Do not treat `600 - 540` as 60 seconds of guaranteed cleanup time. Before managed acceptance, record cold and warm startup/preparation timings (including image preparation where exposed), task/container start, runner entry, terminal result and task completion, with sample count and maximum observed values. Use the lifecycle records below to identify runner entry; when those records are missing, keep the timing gate open rather than treating missing startup time as zero.

Use a conservative acceptance budget: **startup through deadline arming + 540 seconds + cleanup/result-flush time + a recorded safety margin must be below 600 seconds**. Measure cancellation/deadline cleanup as well as successful runs. If it does not fit, stop acceptance and review a shorter runner deadline or a revised platform limit before execution/promotion; do not infer a guarantee from local startup or a warm run. A platform timeout without the runner's terminal record remains an execution failure; earlier committed checkpoints/imports may survive, so inspect retained state before retrying.

Each Job runs as its corresponding foundation identity, reads only its own numbered `DATABASE_URL` secret version and mounts the reviewed instance at `/cloudsql`. Secret contents must already name the matching SQL login, `urbanpulse` database and `/cloudsql/CONNECTION_NAME` socket. Terraform cannot verify secret contents or identity/secret pairing against the live foundation; compare the supplied non-secret outputs before planning. Redis is disabled and mode is fixture. There is no scheduler, HTTP service, execution token or deploy workflow.

Before planning:

1. Complete [foundation](demo-foundation.md) and [private database bootstrap](demo-database.md), retaining verified state backups. Compare foundation outputs with the private `foundation` input object. Check existing Job names for collisions; stop rather than adopt another definition automatically.
2. Select a successful [image publication](image-publishing.md) containing the finite initialization/worker entrypoints. Verify the full commit's CI, publication record, immutable API digest and `org.opencontainers.image.revision` image label agree. Keep that record outside expiring workflow artifacts.
3. Pull that exact image and run both modules with `--help` using `--network none`: `/app/.venv/bin/python -m workers.initialization.job --help` and `/app/.venv/bin/python -m workers.city.job --help`. Verify its expected revision and import ID offline with the command below. Never infer an import ID from the web image or a different checkout.
4. Verify the three numbered secret versions exist and are enabled, each identity has its own secret access plus connector access, and the Cloud Run service agent can pull the same-project image. The applying operator needs Job create/update plus `iam.serviceAccounts.actAs` on the three identities. The authorized execution operator needs Jobs execution permission; no new project-wide role grants are made by this root. Builder identity stays unchanged. Stop if missing access requires a new IAM decision.
5. Copy [example values](../../infra/demo-jobs/terraform.tfvars.example) into ignored `terraform.tfvars`, replacing every placeholder. Use a new explicit run ID when changing import identity; retain the same run ID for a retry. Validate readiness for mutation/restore separately from Job creation; stop legacy writers before running Jobs.

With `$ApiImage` set to the verified API digest, this Windows PowerShell 5.1 / PowerShell 7 command writes only temporary files inside a network-isolated container and opens no database session:

```powershell
docker run --rm --network none --entrypoint /app/.venv/bin/python $ApiImage -c 'import json,tempfile; from pathlib import Path; from urbanpulse.adapters.city_fixture import capture_city; from urbanpulse.adapters.city_store import import_identity; from urbanpulse.adapters.demo_database import EXPECTED_REVISION; d=tempfile.TemporaryDirectory(); print(json.dumps(dict(schema_revision=EXPECTED_REVISION, import_id=import_identity(capture_city(Path(d.name)))))); d.cleanup()'
```

Record the output with the image digest/source SHA. The configured revision and both import/worker IDs must match it. The source SHA label is a record, not cryptographic verification of an arbitrary supplied image.

## Plan, approval and apply

Run from the repository root. The lock file includes Linux, Windows and both macOS architectures. CI performs credential-free mocked plans only.

```powershell
terraform -chdir=infra/demo-jobs init -input=false -lockfile=readonly
terraform -chdir=infra/demo-jobs validate
terraform -chdir=infra/demo-jobs plan "-out=jobs.tfplan"
terraform -chdir=infra/demo-jobs show -no-color jobs.tfplan
```

The first real plan should add exactly three Job definitions, with no modifications/deletions or foundation resources. Review names, image/source, SQL instance, identities, numbered secrets, commands and limits. A mocked plan does not establish live access or count as approval. Keep the saved plan private and submit the actual plan for architect review before apply. If inputs or state change after review, regenerate and review it again.

Before updating definitions, inspect active executions and wait for their terminal results; changing a definition does not change an already running execution. Before and after apply, back up this root's local state when present to the existing private backup location, verify SHA-256 against the source and retain the previous copy; record explicitly when no pre-apply state exists. Never commit state, plans or secret values. Only after approval, apply the reviewed file:

```powershell
terraform -chdir=infra/demo-jobs apply jobs.tfplan
```

Inspect the actual three definitions against the plan before requesting execution. Never use `--execute-now`, a Terraform execution token or an automatic retry. Job definitions have deletion protection; decommissioning requires a separate review and must not delete retained SQL data.

## Runner measurement records

The finite runners preserve their single terminal JSON result on stdout. They also emit two JSON records on stderr with `severity=INFO`, `telemetry_version=1` and a shared random `invocation_id`: `job_runner_started` records UTC entry and the configured deadline; `job_runner_finished` records the outcome, UTC cleanup completion, monotonic runner elapsed time and cleanup elapsed time. Cleanup is included in runner elapsed time. The finish record also contains `deadline_started_at` and monotonic `deadline_offset_seconds`, measured immediately before arming the deadline; include this pre-deadline observation overhead in the startup budget. Both are null if cancellation was already requested before arming. These records contain no credentials, exception text or request payloads. Invalid CLI arguments do not start a runner and therefore have no lifecycle pair.

Correlate the pair with Cloud Run's execution/task/attempt log labels and the unchanged stdout result. Compare platform task start with `runner_entered_at`; compare `cleanup_completed_at`, the terminal-result log and platform task completion to account for result flushing and exit. The finish timestamp precedes telemetry/result output: it is not evidence that those logs were flushed or that the container has exited. A missing finish record, including on OOM/SIGKILL, leaves timing and memory acceptance open. Do not treat an `INFO` lifecycle record as terminal success.

Memory evidence is read from the process's current memory cgroup, resolved through `/proc/self/cgroup` and `/proc/self/mountinfo`, supporting v2 and v1. `cgroup_lifetime_peak_bytes` reads the kernel high-water counter; `cgroup_peak_at_runner_entry_bytes` records its baseline. The counter is read after child cleanup and is never reset; later telemetry/result serialization and process-exit allocations are outside that reading. It can include startup, descendants, charged cache/kernel memory and other processes sharing that cgroup. Verify that scope matches the isolated Job container before using it for sizing; it is not per-process RSS or an isolated invocation delta. Do not subtract the two high-water marks to infer invocation memory.

`sampled_max_bytes` is separately obtained from current usage at entry, supervision polls and after cleanup. Its `sample_count` describes observations, not a guaranteed interval or lifetime peak. Sampling can miss short spikes. Missing/inaccessible counters or unsupported platforms produce `null` values; Windows does not report fabricated zero usage. A telemetry sink failure does not turn completed work into a failed mutation. Cloud Monitoring samples remain corroborating evidence, not a replacement for a missing peak counter.

Reference: kernel [cgroup v2 memory interfaces](https://docs.kernel.org/admin-guide/cgroup-v2.html#memory) and [v1 memory controller](https://www.kernel.org/doc/Documentation/cgroup-v1/memory.txt). After publishing this instrumentation, review the pinned image update and perform a separately approved managed rehearsal. Local cgroup checks do not establish Cloud Run counter availability or close cold/warm/deadline acceptance.

## Manual execution and acceptance

Execution is a separate approved mutation. For the selected project and region, invoke `gcloud run jobs execute JOB_NAME --project PROJECT_ID --region australia-southeast2 --wait`, replacing placeholders with inspected values. Execute migration, then import, then worker, checking each terminal execution and structured `status=complete` log before the next step. Do not use argument/environment/task overrides; change and review the definition instead. An accepted submission or successful configuration apply is not execution success.

| Given / when | Required evidence |
| --- | --- |
| Fresh configured Jobs, explicit approved executions | Migration exact revision, import exact identity/active selection, worker second 360 and both lanes complete; record execution IDs and digest |
| Same successful request repeated | Same import/run; no extra immutable input or delivery effects |
| Incorrect import pin in a reviewed failure rehearsal | Nonzero result, no new import/history rows, active selection unchanged |
| Second mutation execution overlaps | One owner; other invocation reports busy; observed sessions stay within role caps |
| Cancellation/deadline or connector interruption | Nonzero status, lock/session released; retained committed history preserved and explicit retry resumes |
| Secret/SQL access denied | Nonzero execution, redacted diagnostics, no subsequent Job or serving promotion |
| Cold/warm startup and deadline rehearsal | Timestamped startup/runner/cleanup evidence and an explicit safety margin fit inside the task budget; missing timing evidence or only a platform timeout blocks acceptance |
| Actual configuration/read-back | Correct three identities/secrets, socket, immutable image, limits, logs; record peak sessions/memory and elapsed time |

Use a separately approved disposable target for failure rehearsals; do not edit live secrets to induce errors. A definition rollback changes the image/configuration only: verify schema compatibility and never downgrade or erase history. Restore rehearsal and IAP serving promotion remain separate gates. See [worker recovery](city-job.md) and [initialization recovery](initialization-jobs.md).

References: [Cloud Run Jobs creation](https://docs.cloud.google.com/run/docs/create-jobs), [execution](https://docs.cloud.google.com/run/docs/execute/jobs), [task timeouts](https://docs.cloud.google.com/run/docs/configuring/task-timeout), and the pinned provider's [Job schema](https://registry.terraform.io/providers/hashicorp/google/7.46.1/docs/resources/cloud_run_v2_job).

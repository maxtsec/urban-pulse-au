# Managed Job definition verification

Verified locally on 6 October 2026. Procedure: [managed Jobs](../runbooks/managed-demo-jobs.md). Progress: [delivery plan](../delivery-plan.md).

Validation passed: all three Terraform roots initialized with read-only locks and validated; 13 Job mocked plans and 5 foundation mocked plans passed, along with 10 workflow/deployment-consistency unit tests, actionlint, Ruff lint/format and 623 local documentation file links. A freshly built Linux API image loaded both finite CLI modules with `--help` and computed the expected revision/import identity with network disabled; no database or cloud connection was made by these commands.

Review follow-up: the documented offline command succeeded in Windows PowerShell 5.1.26100.9444 against the Linux image. It avoids embedded double quotes, with a regression guard. A second consistency check ties the deployed worker target to the application `MAX_SECONDS`. Managed startup/deadline timing is still unverified: acceptance now requires cold/warm startup, cleanup, terminal-result evidence and a recorded margin within the 600-second platform budget.

The new Terraform root reuses the foundation output contract and pins existing identities, numbered secret versions and one immutable API image. It defines migration, import and worker Jobs without executing them or changing foundation/IAM resources.

Credential-free mocked plans check the three finite commands, paired identities/secrets, managed SQL socket, fixture-only/no-cache environment, one task, no task retry, timeout headroom and source/image records. Negative plans reject mutable/foreign/web images, missing or aliased secret versions, unreviewed schema revisions, invalid import/source/run IDs, a foreign database and reused identities/secrets. The shared multi-platform provider lock is used read-only, and CI validates this root alongside bootstrap and foundation.

Mocked plans do not verify real image availability, IAM, secret contents, managed sockets, runtime resources, restore or execution success. The runbook defines the actual plan review, state backup and separately approved execution acceptance before serving promotion.

## First managed executions and measurement gap

The approved definitions were read back against commit `aa69228f2df5c8a4daa8fd3109f0727454f3c837` and immutable API manifest `sha256:6c4c2eacec65d1dfef0c949f9b8da0074cc4a7592f408522d1664ec38ce143bb`. Terraform reconciliation reported zero changes; local state backups were hash-verified. After checking for active executions, application database sessions and the shared mutation lock, each Job was manually executed once with no argument overrides or automatic retry.

| Job | Submission to completion | Platform start to completion | Verified result |
| --- | ---: | ---: | --- |
| Migration | 19.2 s | 11.6 s | `complete`, revision `0007_city_checkpoints` |
| Import | 15.0 s | 9.6 s | `complete`, expected immutable import selected |
| Worker | 25.8 s | 21.7 s | `complete`, import-bound run at second 360 |

Read-only database verification found 17 complete checkpoints, 39 complete location deliveries and 9 complete result deliveries, with no remaining application session or mutation lock. There was no platform OOM/timeout or failed task. These are one successful execution per Job, not repeated-run or failure-recovery evidence.

After allowing metric ingestion, the worker had one memory sample of 123,555,840 bytes (117.8 MiB). Migration/import had no positive memory samples. This is not a verified peak. Approximately one-second session sampling observed one worker connection and missed the shorter migration/import sessions; it does not prove their session peaks. The image did not emit runner-entry timing. Private execution IDs, logs, metrics, database checks and state hashes are retained locally.

The follow-up adds lifecycle timestamps and cgroup high-water evidence, while preserving stdout results and resource/deadline settings. Native-counter availability, cold/warm startup, deadline cleanup, repeat execution, disposable failure/overlap rehearsals and restore remain acceptance work before serving promotion. See the [measurement procedure](../runbooks/managed-demo-jobs.md#runner-measurement-records).

Local instrumentation verification covers cgroup v1/v2 resolution, missing counters, sampled-versus-native peaks, sanitized failure records and unchanged terminal results. In a network-disabled Linux container, a short-lived child allocating 64 MiB raised the v2 lifetime counter from 19,697,664 to 90,984,448 bytes while entry/finish sampling saw only 20,160,512 bytes. This confirms child spikes can survive between polls in that local kernel; it is not a Cloud Run availability claim. Real PostGIS entrypoint tests cover successful/repeated execution, rejected targets, held mutation locks, timeouts and cancellation with the additional lifecycle records.

Validation for the instrumentation follow-up: Ruff lint/format and mypy passed; 539 unit tests and 21 real PostGIS finite-job integration tests passed. The isolated Compose smoke passed under `python -O`, including the packaged finite worker, database restart recovery and optional Redis modes; its project resources and recorded volume mounts were removed. Frontend code was unchanged; browser checks remain in CI.

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

Review follow-up: observation methods now fence ordinary exceptions independently of business supervision. Injected discovery, sampling, final-peak, clock and sink failures preserve child completion and the original operation exception; process-control signals remain visible. A pre-cancelled runner verifies paired null deadline fields through the shared evidence checker. Ruff lint/format, mypy, 547 unit tests and the 21 PostGIS Job integration tests passed after these fixes.

## Managed telemetry and idempotent repeat

On 6 October 2026, the architect-approved saved update plan changed only the three Jobs' image/source pins to `f4e74e858cc3ebd554add58d82363627f133a1ab`, API manifest `sha256:a8fe1b5f9fa6c01070dec8ec840c732b296abcb0b2189156e00b5b4de44ddef0`. The exact publication and image were verified; both finite entrypoints and the unchanged schema/import identity were checked offline. Apply updated three definitions with no additions/deletions. Read-back preserved commands, identities, secrets, socket and limits; reconciliation was empty and state backups matched their source hashes.

Each Job was then explicitly run once with the existing import/run IDs. All platform and stdout results were complete, with correlated start/finish lifecycle records:

| Job | Submission to completion | Runner elapsed | Native cgroup peak read after cleanup |
| --- | ---: | ---: | ---: |
| Migration | 16.1 s | 1.34 s | 172.3 MiB |
| Import | 13.8 s | 1.42 s | 171.1 MiB |
| Worker | 12.0 s | 1.13 s | 164.2 MiB |

The managed environment exposed v1 memory counters. These are container-cgroup lifetime high-water readings including descendants and charged startup/cache/kernel memory, taken before final telemetry/result flushing and exit; not per-process RSS, an invocation delta or the final whole-task peak. This measures the already-complete repeat path, not fresh processing or serving load.

Read-only before/after comparisons of row counts and SHA-256 of sorted full JSON row contents matched across all 19 application/schema tables. The original 17 checkpoints and 48 deliveries remained complete; no application connection or mutation lock remained. Session sampling observed zero/one/one migration/import/worker connections, with maximum observed sample gaps around 1.21/1.08/1.10 seconds. Short connections may be missed, so zero is not absence and these are not exact peaks.

Cold/warm repeated startup with an explicit margin, deadline/cancellation cleanup, disposable overlap/failure rehearsals and restore are still required for full managed acceptance. Private execution IDs, paired logs, fingerprints, plan and backup hashes remain in ignored local evidence. See [delivery status](../delivery-plan.md).

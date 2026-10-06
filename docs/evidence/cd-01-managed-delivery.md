# CD-01 managed delivery evidence

Recorded 7 October 2026 (Australia/Sydney). Progress is maintained in the [delivery plan](../delivery-plan.md).

## Executions

- Source: `e5e7484e47db63bedfe21227a290b9eb084fb4a0`, published by [images run 37452828509, attempt 2](https://github.com/maxtsec/urban-pulse-au/actions/runs/37452828509/attempts/2). Checks, Compose, Terraform and both image publications passed.
- [Automatic candidate run 37458151894](https://github.com/maxtsec/urban-pulse-au/actions/runs/37458151894) succeeded. The independent GitHub-federated deployer read GCS state, checked image/schema/import compatibility, saved its bounded plan and created a Ready revision with zero default traffic. The existing serving revision retained 100%.
- [Protected promotion run 37541654600](https://github.com/maxtsec/urban-pulse-au/actions/runs/37541654600) records the operator-authorized dispatch and required environment approval. It succeeded: the retained candidate receives 100%, the candidate tag was removed, the previous serving release is retained for rollback, and both deployment locks are absent. Images were not rebuilt.

## Retained evidence and recovery

The private versioned GCS bucket retains the serving state, deployment pointer, before/after state copies and saved plan. Named immutable image pairs and full source SHA identify the release; no phase tag or production release was created. Promotion retains the former serving record as `previous`. Rollback follows the traffic-only saved-plan procedure in the [CD runbook](../runbooks/managed-demo-cd.md), after schema/import compatibility and state checks. It is never an automatic state downgrade.

Both GitHub environments restrict deployments to main; promotion requires the named operator. The operator confirmed administrator bypass was disabled in both settings pages. API reads establish the reviewer/branch rules; the UI-only bypass setting is operator-confirmed, not independently observed.

## Limits

Successful authentication and cloud operations establish the trusted path. Read-back confirmed the deployed repository/main/workflow/environment trust constraints, but a live exchange from an untrusted context has not been performed. That negative test remains open. Existing operator browser acceptance was not repeated; Ready and traffic read-back establish deployment behavior, not new functional/performance acceptance. This remains a protected fixture demo, not production or live-source enablement.

# Managed Job definition verification

Verified locally on 6 October 2026. Procedure: [managed Jobs](../runbooks/managed-demo-jobs.md). Progress: [delivery plan](../delivery-plan.md).

Validation passed: all three Terraform roots initialized with read-only locks and validated; 13 Job mocked plans and 5 foundation mocked plans passed, along with 10 workflow/deployment-consistency unit tests, actionlint, Ruff lint/format and 623 local documentation file links. A freshly built Linux API image loaded both finite CLI modules with `--help` and computed the expected revision/import identity with network disabled; no database or cloud connection was made by these commands.

Review follow-up: the documented offline command succeeded in Windows PowerShell 5.1.26100.9444 against the Linux image. It avoids embedded double quotes, with a regression guard. A second consistency check ties the deployed worker target to the application `MAX_SECONDS`. Managed startup/deadline timing is still unverified: acceptance now requires cold/warm startup, cleanup, terminal-result evidence and a recorded margin within the 600-second platform budget.

The new Terraform root reuses the foundation output contract and pins existing identities, numbered secret versions and one immutable API image. It defines migration, import and worker Jobs without executing them or changing foundation/IAM resources.

Credential-free mocked plans check the three finite commands, paired identities/secrets, managed SQL socket, fixture-only/no-cache environment, one task, no task retry, timeout headroom and source/image records. Negative plans reject mutable/foreign/web images, missing or aliased secret versions, unreviewed schema revisions, invalid import/source/run IDs, a foreign database and reused identities/secrets. The shared multi-platform provider lock is used read-only, and CI validates this root alongside bootstrap and foundation.

Mocked plans do not verify real image availability, IAM, secret contents, managed sockets, runtime resources, restore or execution success. The runbook defines the actual plan review, state backup and separately approved execution acceptance before serving promotion.

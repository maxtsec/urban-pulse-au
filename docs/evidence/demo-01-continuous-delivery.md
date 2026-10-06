# Managed CD implementation verification

Verified locally on 6 October 2026. Scope: [ADR 0014](../adr/0014-managed-demo-continuous-delivery.md) and [activation/recovery runbook](../runbooks/managed-demo-cd.md).

- Ruff lint/format and strict mypy passed, including the new deployment modules.
- The full unit suite passed: 586 tests, with 181 integration cases deselected. The 37 CD cases were rerun after the final seed/rollback-record change and passed. They cover trusted publication/run attempts, forbidden resource/IAM/security changes, incompatible migrations/imports, superseded promotion, operation overlap and failure recovery through the real runner entrypoint with fake external boundaries.
- Terraform validate and two mocked CD plans passed, including rejection of a migration identity in place of runtime. All 24 existing serving mocked plans passed. The copied provider lock retains the same reviewed platform checksums.
- Pinned actionlint passed for the workflows. New workflow actions are SHA-pinned, CD is opt-in and promotion uses a protected environment. Builder trust/hardening and registry cleanup remain separate work.
- The plan guard accepted the privately retained real candidate and traffic-only promotion plans. No new cloud plan or apply was performed for this implementation.
- The new API metadata command ran successfully against the existing cached image in a non-root, read-only container with no network or credentials, and matched the accepted schema/import identity.
- All 673 local documentation targets checked at the final implementation pass resolved. Whitespace checks passed.

This verifies implementation behavior locally. No bucket/deployer was provisioned, backend/state was migrated, GitHub environment was changed, CD was enabled, or hosted acceptance was repeated. Live federation, least-privilege API compatibility and a first managed workflow execution are activation evidence, not results of mocks. Merge does not deploy or change the accepted running demo.

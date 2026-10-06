# DEMO-01 managed database initialization evidence

Verified: 6 October 2026 (Australia/Sydney). Procedure: [database runbook](../runbooks/demo-database.md). Decisions: [ADR 0012](../adr/0012-managed-demo-resource-profile.md). Current delivery status: [delivery plan](../delivery-plan.md).

## Foundation and private initialization

The explicitly approved saved foundation plan was applied from merged commit `d711acc`: **22 additions, zero changes, zero deletions**. The Cloud SQL API was enabled first and instance-name absence verified. Resource readback matched the protected Melbourne zonal PostgreSQL 17 profile. The subsequent Terraform plan returned `No changes`. A timestamped private state copy was checksum-verified and retained outside the worktree.

Private initialization installed PostGIS, applied the seven existing migrations through `0007_city_checkpoints` as `urbanpulse_migrate`, set the closed [privilege matrix](../runbooks/demo-database.md#privilege-matrix), and published version **1** of each existing runtime/migrate/import/worker database-URL secret. All four stored payloads were privately compared with the intended role/socket URL. Generated passwords, URLs, operator recovery material and Terraform state were excluded from Git and test output. The temporary Auth Proxy was stopped after verification.

| Managed observation/check | Result |
| --- | --- |
| PostgreSQL / PostGIS | PostgreSQL 17; observed PostGIS **3.6.4**, GEOS 3.11.4 (local test image is PostGIS 3.5) |
| Migration ownership | Application tables belong to the migration role; database/extension ownership stays with the operator/platform |
| Role attributes | Four logins; no superuser, database/role creation, replication, bypass-RLS, inheritance or administrative membership |
| Actual connection settings | `max_connections=50`, `superuser_reserved_connections=3`, `reserved_connections=0` |
| Connection-cap exercise | Real connections up to runtime 12 / migrate 2 / import 3 / worker 4 succeeded; one extra connection for each role was rejected; all test sessions closed |
| Baseline after cap tests | Two platform client sessions and one operator session; with the three reserved slots this fits the ten-slot planning allowance; this is one observation, not a permanent usage bound |
| Permissions | Runtime reads/spatial calls succeed; runtime/import event writes and worker input writes are denied |
| Managed spatial compatibility | **25 existing integration cases passed** through the runtime role: transport point/boundary membership, weather polygon overlap/holes/invalid geometry, and planning/combined city fixtures |

## Reproducible local security tests

Local validation passed: **494 unit tests**, **155 integration tests** (including **13 database-bootstrap security cases**), Ruff lint/format and strict mypy over 56 source files. All 546 relative documentation links resolved.

The new integration module uses a random disposable database and four randomly prefixed roles on a separate local PostgreSQL/PostGIS server. It verifies real login, migration ownership, allowed input/pointer/effect writes, denied cross-context writes, denied DDL/temp/truncate/role escalation, future table/sequence/function privacy, unknown-table refusal, safe repeat refusal and connection exhaustion. The suite also rejects autocommit initialization and accidental credential rotation.

Reproduce with `uv run pytest -m integration -q tests/integration/test_demo_database.py`. These checks run in ordinary CI without cloud credentials. Managed spatial checks were a separate operator run against the new Cloud SQL database using the existing three spatial test modules; the full destructive integration suite was not pointed at cloud resources.

The observed PostGIS version differs from the local image, so the managed pass is recorded explicitly rather than inferred from local results. Authentication used the operator's Auth Proxy identity plus each SQL login; deployed service-identity/IAP checks, fixture import, backup restore, shared API pooling and bounded Job execution remain the [deployment gates](../runbooks/demo-database.md#verification-and-remaining-deployment-gates).

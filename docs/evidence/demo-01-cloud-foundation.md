# DEMO-01 foundation validation

Date: 6 October 2026. Scope: [ADR 0012](../adr/0012-managed-demo-resource-profile.md) and the [foundation root](../../infra/demo-foundation). Progress: [delivery plan](../delivery-plan.md).

This is the initial pre-apply validation record; subsequent apply and private database checks are recorded in [database initialization evidence](demo-01-database-bootstrap.md).

The selected profile is encoded in Terraform with Google provider 7.46.1 locked. Mocked validation is credential-free. A separate operator-authenticated plan was prepared read-only; no apply, IAM write, secret value, database creation, reviewer grant or Job execution was performed.

| Verification | Result |
| --- | --- |
| Terraform format and validate | Passed |
| Mocked `database_safety` plan | Accepted region/tier/version, protected instance/database, fixed SSD storage, connector-only encrypted access and backup/PITR policy passed |
| Mocked `identity_separation` plan | Four distinct identities, paired secret readers, protected regional secret containers and API ownership/preservation passed |
| Mocked `connection_headroom_and_execution_contract` plan | Six planned API process slots at two connections each, all three job budgets, operational reserve, manual bounded worker and organization-only audience contract passed |
| Invalid project/prefix plans | Both rejected at variable validation |

## Operator plan

The actual target-project plan reports **22 additions, 0 changes and 0 deletions**, matching the foundation inventory. Secret Manager was already enabled; its plan entry represents Terraform ownership of that API setting. Cloud SQL, Cloud Run and IAP were not enabled during inventory, and were not enabled by preparing the plan. No matching identity/secret names were found in the enabled services. SQL instance-name absence could not be verified while its API was disabled; recheck after enablement before creating/adopting the database, and stop on a name collision rather than replacing anything.

The plan and JSON/log are saved under ignored `.local/demo-foundation*`. They are private review artifacts, not committed state or deployment evidence. A fresh plan still needs review if configuration or remote state changes. No bootstrap resource or builder trust change appears in this plan.

Five mocked test runs passed. Reproduce with the [foundation runbook](../runbooks/demo-foundation.md#validate-without-credentials). These tests check planned provider values and connection arithmetic; they do not simulate PostgreSQL connection saturation, Cloud Run overshoot, real IAM, IAP, restore or throughput.

The runtime contract totals 21 client slots, 10 reserved/operator slots and 19 unallocated against the configured 50. Actual database roles and serving/job settings are not created here. Shared API pooling, finite waits, global role limits, Job execution locks and capacity/overlap tests are explicit deployment gates in the [resource plan](../architecture/demo-cloud-resource-plan.md#connection-envelope). Current unbounded application connections cannot be declared safe merely because these plan tests pass.

The existing publishing proof remains tied to [main run 37388784051](https://github.com/maxtsec/urban-pulse-au/actions/runs/37388784051); this foundation does not replace its images or alter builder federation. Issues #28, #29 and #30 remain unimplemented.

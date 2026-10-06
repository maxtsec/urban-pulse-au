# Managed fixture continuous delivery

Decision: [ADR 0014](../adr/0014-managed-demo-continuous-delivery.md). This adds application delivery to the existing [managed serving root](managed-demo-serving.md). It does not change the current cloud deployment when merged. Keep `DEMO_CD_ENABLED` unset or `false` until setup is reviewed and complete.

## One-time setup, separately approved

1. Review `infra/demo-cd` with private inputs. Its dedicated bucket is versioned, denies public access, prevents Terraform destruction and has no automatic history cleanup. The independent deployer has only the existing service update scope, runtime act-as, image reads, metadata reads and dedicated object access. No service-account key or builder privilege is added. Save/review the actual plan, then obtain approval before applying it. Keep its local state backed up before/after, including partial failures.
2. Freeze all local/CI serving writes and initialization Jobs during migration. Back up current `infra/demo-serving/terraform.tfstate`, `terraform.tfstate.backup` if present, and the **currently applied** private serving inputs; verify SHA-256 and retain earlier backups. Do not use old empty-audience bootstrap inputs. Confirm the source state's lineage/serial and the expected three resources. Confirm the destination `serving/default.tfstate` is absent; an existing remote state needs reconciliation, never an overwrite.
3. After the migration itself is approved, copy `infra/demo-serving/backend.tf.example` to ignored `backend.tf`. Run `terraform -chdir=infra/demo-serving init -migrate-state "-backend-config=bucket=REVIEWED_BUCKET" "-backend-config=prefix=serving"`. Do not use `-force-copy`. Review the migration prompt. Read remote state back, compare lineage/serial/resources with the backup, and require a no-resource-change plan using the current private inputs. Retain both old and new bytes/hashes privately. Do not run the old local backend again; restoring a previous state is an explicit recovery operation, not rollback.
4. With no candidate outstanding, seed a private accepted record from the promoted serving inputs:

```powershell
uv run --locked python -m scripts.demo_delivery_seed --inputs .local/current-serving.tfvars.json --output .local/delivery-current.json --acceptance-reference retained-private-acceptance
```

The paths are examples: use the verified currently applied input file and a real private acceptance reference. If a previous accepted rollback revision exists, also pass `--previous-inputs` with its retained input file and use an acceptance reference covering both revisions; preserve that rollback record during CD adoption. The seed tool makes no cloud call and does not verify the deployment by itself. Review the JSON, then upload it to `delivery/current.json` in the dedicated bucket using an authenticated operator and an object-generation precondition of zero. Do not overwrite an existing deployment record. Retain the initialized schema/import and secret-version evidence. API startup does not initialize or select fixture data.

5. Configure repository variables `GCP_PROJECT_ID`, `GCP_DEPLOY_WORKLOAD_IDENTITY_PROVIDER`, `GCP_DEPLOYER_SERVICE_ACCOUNT`, `DEMO_STATE_BUCKET` from the reviewed outputs. These belong to the separate deployment identity, not the image builder. Do not store OAuth/database secrets or state in GitHub variables/artifacts.
6. Create `demo-candidate` and `demo-promotion` GitHub environments restricted to main. Require a named human reviewer for `demo-promotion` and disallow administrator bypass. For a solo operator, allow that reviewer to approve their own dispatch; otherwise require a different reviewer. The runner rejects promotion if the environment lacks required reviewers. Review repository branch protection and the exact workflow files; WIF binds both `cd.yml` and reusable `deploy.yml`.
7. Enable `DEMO_CD_ENABLED=true` only after separately approved state migration and identity/environment setup. Activation must prove main federation succeeds and an untrusted trigger/environment is denied, without widening IAM to work around a failure. The offline tests do not establish effective cloud permissions. A successful new main publication triggers delivery; rerunning the trusted publication can also trigger a fresh attempt, provided its SHA is still current main.

The documented [GCS backend](https://developer.hashicorp.com/terraform/language/backend/gcs) provides state locking and recommends versioning. Application delivery adds a separate operation lock because backend locking alone does not serialize release-record updates and the time between plan/apply. The bucket's deployer role is intentionally scoped to this dedicated bucket, not arbitrary project storage.

## Candidate and promotion

`cd.yml` listens only for successful `Publish images` runs and manual promotion dispatch. It is disabled by default. It checks the source repository/main/push boundary; the runner independently verifies the publication run, attempt, immutable manifest, image labels/platform and current main. Workflow code is checked out from the protected workflow SHA, never a downloaded artifact or arbitrary dispatch ref.

The runner reads the private `delivery/current.json`, acquires `delivery/operation.lock` with a generation precondition and initializes the GCS backend. It pulls immutable API/web images; API metadata is read in a network-disabled, read-only, non-root, bounded container with no host mounts. Both the candidate and currently serving API image must have equal Alembic heads, migration fingerprints and deterministic import identities matching the accepted inputs. Any mismatch stops before apply. Initialization Jobs remain an operator-owned separate workflow; disable CD and take the shared operation lock when changing that baseline.

Candidate delivery preserves all existing security, sizing and database settings. Its saved plan must update only the existing service: the two images, source labels, explicit revision and tagged zero-percent target. It retains default traffic on the serving revision. The source commit is rechecked before apply so delayed publication runs cannot replace a newer candidate. A new successful deployment record is written only after revision readiness, digest/security and traffic read-back.

The candidate workflow summary gives the source, revision and two digests. Detailed release records and the tagged URL are available through the private record and Cloud Run Console. Platform readiness is not browser acceptance: authenticate to the candidate-tag URL before promotion. Existing completed acceptance is not rerun by merging this code; this procedure applies to later deployed changes.

To promote, dispatch **Managed demo delivery** on main with the exact retained candidate revision and the acceptance checkbox. Review that revision/digests in its candidate run, then approve the `demo-promotion` environment. The runner re-reads the shared record after acquiring the lock, rejects a superseded candidate and generates a saved plan whose only configurable change is traffic to that revision at 100%, removing the candidate tag. Anything else stops. No image rebuild, new revision, database mutation or IAM write is part of promotion.

The previous accepted serving record becomes `previous`; failed candidates/promotions cannot replace it. Automatic traffic rollback is not enabled. Use a separately reviewed traffic-only rollback plan against this same backend, with current candidate template inputs and the recorded compatible previous revision as `serving_revision`. Preserve data/history and named secret versions. Update the private serving record after the control-plane result is confirmed; do not simply reset state to an earlier version.

## Private records and recovery

- `serving/default.tfstate`: active remote Terraform state, with backend locking and object versions.
- `delivery/current.json`: accepted serving, retained candidate, previous serving, private input records and pending operation identity.
- `delivery/operation.lock`: generation-checked operation lock spanning metadata, plan, apply and record commit. It never expires automatically.
- `delivery/runs/<run-attempt>/`: before/after state copies, narrow-boundary saved plan, release record or private failure diagnostic. These survive Actions artifact expiry. Object names are unique and writes use generation preconditions.

A durable intent is recorded before Terraform apply. If the workflow fails, times out or is interrupted after that point, leave the operation lock and pending record in place. Disable CD, confirm no workflow/Terraform/local operator remains active, and inspect the saved intent, private error, current remote state/version and Cloud Run result. An interrupted update may have succeeded remotely. Reconcile forward to the actual state and release record, retaining prior serving/rollback evidence; do not rerun a stale plan, erase history or force-unlock blindly. Remove only the verified stale lock generation after recovery, then re-enable CD. An exception before mutation releases its own lock and leaves the serving record untouched.

The deployer can operate objects in its dedicated bucket; versioning supports recovery but does not make the audit record immutable against that identity. No lifecycle cleanup is introduced here. Artifact Registry digest-retention and existing builder hardening issues remain separate work; neither is silently implemented by this PR.

## Local verification and limits

Run `uv run --locked pytest tests/unit/test_demo_delivery.py tests/unit/test_demo_delivery_runner.py -q`, Ruff and workflow syntax checks. Run `terraform -chdir=infra/demo-cd init -backend=false -input=false -lockfile=readonly`, `validate` and `test` for credential-free infrastructure validation. The existing serving mocked plans still cover candidate/promotion/rollback topology. Workflow validation CI has no deployment credentials and does not migrate a backend.

Unit tests exercise provenance, forbidden changes, compatibility, superseded selection and the actual runner entrypoint with fake boundaries, including interrupted mutation and lock retention. They do not prove live IAM, cross-process locking, registry availability or first activated CD execution. No cloud resource, state migration, environment setting or workflow activation is performed by these tests.

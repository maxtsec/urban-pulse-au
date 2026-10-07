# ADR 0014: Managed fixture continuous delivery

Date: 2026-10-06

Status: **Architect accepted the GCS backend and automatic-candidate/manual-promotion direction on 2026-10-06.** Implementation and approved setup are recorded in [CD evidence](../evidence/cd-01-managed-delivery.md). Further infrastructure or security-boundary changes retain their review requirements.

## Decision

Use a dedicated private GCS bucket with object versioning and Terraform locking for the existing serving root, plus private deployment records. The bucket and a separate keyless deployer are owned by `infra/demo-cd`; bootstrap state remains local with verified backups. Existing foundation/Job state and the image-builder trust policy are outside this change.

After a successful main image publication with changed image input files, create a named zero-default-traffic candidate. Compare against the retained candidate (otherwise serving) source tree; documentation-only publications preserve a candidate under acceptance. Actual application changes can supersede it. Keep the current verified serving revision at 100%. Promotion requires explicit workflow dispatch naming the retained candidate, confirmation of its acceptance and the protected `demo-promotion` environment. Reject a superseded candidate. Both operations generate saved Terraform plans and enforce a narrow change boundary before apply: candidate images/source/revision plus zero-traffic tag, or promotion traffic only. No IAM, resource creation/deletion, sizing, runtime-secret, database or Job changes are allowed through this workflow.

Routine CD requires the same initialized schema/migration/import identity and the full normalizer/clock/policy/run/codec compatibility tuple defined by the 7 October amendment below. Changes stop for separately reviewed migration/import/worker work and a deployment-record update; schema and data changes are not automated. The original 6 October guard covered only schema/migration/import identity; it remains the current runtime until the extension is implemented.

## State and recovery

GitHub serializes the environment without cancelling running deliveries. A generation-checked GCS operation lock protects the complete read/plan/apply/record sequence, in addition to Terraform's backend lock. A durable intent is written before mutation. A failed or interrupted mutation retains that intent/lock for operator recovery; it cannot overwrite the serving/rollback record or silently unlock and continue. A lock records its creation time and workflow run/attempt even before intent. Hard termination before intent requires the runbook's explicit stale-lock recovery; it is never automatically released by age. An old publication is rejected against current main before candidate apply. GitHub may replace a pending queued run; publication identity, not queue order, controls eligibility.

Successful records retain source SHA, publication run/attempt, image digests, schema/import and migration fingerprints, private inputs, serving/candidate/previous identities, and deployment run. Before/after state copies and the saved plan stay in the private versioned bucket. This is recoverable storage, not a tamper-proof audit log: the deployer can administer objects in that dedicated bucket. Cloud Audit Logs and branch/environment protection remain complementary controls.

## Security boundary

A new federation pool accepts only this repository's immutable IDs, main, the dispatcher and reusable deployment workflow, and the matching trigger/environment pair. Candidate runs use `workflow_run` and `demo-candidate`; promotion uses `workflow_dispatch` and `demo-promotion`. The builder's existing deferred hardening work is unchanged.

The deployer can update the existing named Cloud Run service and act as only its runtime identity. It can read images and deployment metadata and operate the dedicated state bucket. It cannot administer IAM, create/delete services, execute migration/import Jobs or directly read Secret Manager values. Updating a service running as runtime is nevertheless indirect access to runtime data; protecting workflow code and the promotion environment is part of that boundary. Platform IAM permissions alone cannot distinguish an image update from a traffic change; reviewed code enforces that distinction.

Published image metadata is read in a bounded offline container with no network, credentials, host mounts or privileged capabilities. Only JSON publication artifacts from the successful main image workflow are consumed; artifact code is never checked out or executed. Private Terraform output and failure diagnostics are not uploaded to public Actions artifacts.

## MAP-02 serving and compatibility amendment

Date: 2026-10-07. **Accepted by the project architect in PR #48**, alongside the MAP-02 contract and ADR 0011 amendment. This extends the 6 October compatibility decision; implementation is still required. Resource apply, IAM changes, Job execution and traffic promotion remain separate approvals.

A clock-generation rollout needs old and new imports/algorithms to coexist. Updating images while selecting the shared active import cannot isolate a zero-traffic candidate from the serving revision. The accepted decisions are:

| Decision | Accepted rule | Control retained |
| --- | --- | --- |
| Revision-local input | `CITY_IMPORT_ID` pins the exact retained import for each revision; its release descriptor pins the normalizer, fixture clock, policy and run versions | Missing/incompatible pin fails readiness; no silent active-import fallback; same selector for area/animation/evidence |
| Staged import | The reviewed initialization Job gains an explicit persist-and-verify-without-activation mode | Shared active pointer remains on the v1 import; migration/import roles and approval remain separate from the deployer |
| Reader/writer compatibility | New writer uses `city-normalizer-v3`; a version-dispatched reader supports stored v2 seconds and v3 milliseconds, verifying legacy hashes before in-memory conversion | Unknown format fails; old rows/IDs stay unchanged; old-image API reads and v1 worker recovery remain compatible; old import/migrate Jobs intentionally reject DB revisions beyond `0007_city_checkpoints` |
| Release compatibility | Extend records/guards with `normalizer_version`, `clock_version`, `policy_version`, `run_version` and readable observation-codec versions, alongside existing schema/migration/import identity and digests | Version changes stop automatic CD for separately reviewed migration/import/worker steps; no implicit upgrade |
| Selector changes | Initial pin installation or an import/version change uses a separately reviewed serving plan and deployment-record update | Routine candidate/promotion allowlists remain image/revision and traffic only; normal CD keeps the accepted pin/version tuple fixed |

Prefer revision-local pins over changing the shared pointer, which would also change the old revision, or introducing a second database solely for a fixture clock migration. Pins require version-aware readers, a non-activating import path and compatibility rehearsal; they do not grant the deployer database mutation or Job-execution authority. `CITY_IMPORT_ID` is an import identity, not a secret, but its exact selected value belongs in the reviewed deployment record/plan.

Implementation must atomically retain the complete descriptor for serving/candidate/previous revisions and fail if image metadata, selected import or configured pin disagrees. An old record lacking these new fields is not silently assumed compatible: inspect and backfill its verified legacy descriptor through the approved baseline-update procedure. Admission of a new baseline is operator-reviewed; subsequent same-version image updates can resume normal CD. Candidate verification must show the v1 revision still serves its old import and the v2 revision serves only its pinned import. Rollback selects the retained compatible revision/descriptor, never rewrites the shared pointer or reinterprets old normalized rows.

The [rollout/recovery procedure](../runbooks/map-02-clock-migration.md) defines the concrete sequence and v1 worker recovery path. Approval on 2026-10-07 is recorded with ADR 0011, the contract and delivery plan. This amendment is the normative MAP-02 compatibility rule; the original three-field guard is retained above solely to describe the pre-MAP-02 runtime.

## Consequences

Activation requires creating the bucket/identity grants, migrating the existing serving state, seeding the accepted serving record, configuring both environments and enabling an explicit repository flag. Repository merge alone does none of these. Subsequent applications use immutable image pairs; no source rebuild is part of deployment. Manual local operations must respect the shared operation lock and backend rather than using an abandoned local state.

Local mocks establish guard behavior, not live federation permissions or managed rollout behavior. The first activated workflow must establish those separately. Production release, live collection and additional review audiences retain their existing decisions.

References: [GCS backend locking and versioning](https://developer.hashicorp.com/terraform/language/backend/gcs), [workflow_run security boundaries](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_run), [Google deployment federation](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines), [operations](../runbooks/managed-demo-cd.md).

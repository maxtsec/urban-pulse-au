# ADR 0014: Managed fixture continuous delivery

Date: 2026-10-06

Status: **Architect accepted the GCS backend and automatic-candidate/manual-promotion direction on 2026-10-06.** Implementation is submitted for PR review; provisioning, state migration, environment protection and activation require separately reviewed setup. This decision does not apply resources.

## Decision

Use a dedicated private GCS bucket with object versioning and Terraform locking for the existing serving root, plus private deployment records. The bucket and a separate keyless deployer are owned by `infra/demo-cd`; bootstrap state remains local with verified backups. Existing foundation/Job state and the image-builder trust policy are outside this change.

After a successful main image publication with changed image input files, create a named zero-default-traffic candidate. Compare against the retained candidate (otherwise serving) source tree; documentation-only publications preserve a candidate under acceptance. Actual application changes can supersede it. Keep the current verified serving revision at 100%. Promotion requires explicit workflow dispatch naming the retained candidate, confirmation of its acceptance and the protected `demo-promotion` environment. Reject a superseded candidate. Both operations generate saved Terraform plans and enforce a narrow change boundary before apply: candidate images/source/revision plus zero-traffic tag, or promotion traffic only. No IAM, resource creation/deletion, sizing, runtime-secret, database or Job changes are allowed through this workflow.

Only releases with the same Alembic head, migration-file fingerprint and deterministic fixture import identity as the initialized serving release are eligible. Changes stop for the separately reviewed migration/import Jobs and deployment-record update. This first CD slice deliberately does not automate schema or data changes.

## State and recovery

GitHub serializes the environment without cancelling running deliveries. A generation-checked GCS operation lock protects the complete read/plan/apply/record sequence, in addition to Terraform's backend lock. A durable intent is written before mutation. A failed or interrupted mutation retains that intent/lock for operator recovery; it cannot overwrite the serving/rollback record or silently unlock and continue. A lock records its creation time and workflow run/attempt even before intent. Hard termination before intent requires the runbook's explicit stale-lock recovery; it is never automatically released by age. An old publication is rejected against current main before candidate apply. GitHub may replace a pending queued run; publication identity, not queue order, controls eligibility.

Successful records retain source SHA, publication run/attempt, image digests, schema/import and migration fingerprints, private inputs, serving/candidate/previous identities, and deployment run. Before/after state copies and the saved plan stay in the private versioned bucket. This is recoverable storage, not a tamper-proof audit log: the deployer can administer objects in that dedicated bucket. Cloud Audit Logs and branch/environment protection remain complementary controls.

## Security boundary

A new federation pool accepts only this repository's immutable IDs, main, the dispatcher and reusable deployment workflow, and the matching trigger/environment pair. Candidate runs use `workflow_run` and `demo-candidate`; promotion uses `workflow_dispatch` and `demo-promotion`. The builder's existing deferred hardening work is unchanged.

The deployer can update the existing named Cloud Run service and act as only its runtime identity. It can read images and deployment metadata and operate the dedicated state bucket. It cannot administer IAM, create/delete services, execute migration/import Jobs or directly read Secret Manager values. Updating a service running as runtime is nevertheless indirect access to runtime data; protecting workflow code and the promotion environment is part of that boundary. Platform IAM permissions alone cannot distinguish an image update from a traffic change; reviewed code enforces that distinction.

Published image metadata is read in a bounded offline container with no network, credentials, host mounts or privileged capabilities. Only JSON publication artifacts from the successful main image workflow are consumed; artifact code is never checked out or executed. Private Terraform output and failure diagnostics are not uploaded to public Actions artifacts.

## Consequences

Activation requires creating the bucket/identity grants, migrating the existing serving state, seeding the accepted serving record, configuring both environments and enabling an explicit repository flag. Repository merge alone does none of these. Subsequent applications use immutable image pairs; no source rebuild is part of deployment. Manual local operations must respect the shared operation lock and backend rather than using an abandoned local state.

Local mocks establish guard behavior, not live federation permissions or managed rollout behavior. The first activated workflow must establish those separately. Production release, live collection and additional review audiences retain their existing decisions.

References: [GCS backend locking and versioning](https://developer.hashicorp.com/terraform/language/backend/gcs), [workflow_run security boundaries](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_run), [Google deployment federation](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines), [operations](../runbooks/managed-demo-cd.md).

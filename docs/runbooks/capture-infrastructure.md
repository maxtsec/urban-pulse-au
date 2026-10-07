# CLOUD-01 landing and monitoring infrastructure

Use `infra/capture` for the [ADR 0019](../adr/0019-capture-infrastructure-and-monitoring.md) configuration. It provisions a protected private landing bucket, one collector account, bucket-scoped create/get permissions, project-scoped time-series write, eight metric descriptors and seven disabled-by-default alert policies. It does not create a service-account key, deploy the exporter/uploader, start collection or enable raw/cloud expiry.

## Local validation

From the checkout, with the repository's Terraform version:

```powershell
terraform -chdir=infra/capture init -backend=false -input=false -lockfile=readonly
terraform -chdir=infra/capture validate
terraform -chdir=infra/capture test
```

On 2026-10-08, readonly init, validate and all 10 mocked plan tests passed on Windows and in an isolated Linux Terraform container. The mocked creation graph contains 23 resources, with no keys, updates or deletions; this is not an actual cloud plan. Workflow syntax, repository formatting and 367 local document links also passed.

The provider lock contains the same verified Windows/Linux/macOS checksums as the other roots. Tests use mocked providers and synthetic limits, without cloud credentials or a live plan. They check private/deletion-safe storage, exact accepted grants, every feed, unknown successes, pending-upload age, scoped filters and enrollment/channel/input rejection.

## Prepare the private plan

1. Confirm project, billing, Melbourne region and globally unique bucket/account/custom-role names. Storage and IAM APIs are already owned by existing bootstrap/delivery roots; do not import/manage those same API resources in two states. This root owns the Monitoring API enablement and leaves it enabled on destroy. Check effective org policy, inherited IAM and any existing resource collisions before planning.
2. Copy `terraform.tfvars.example` to ignored `terraform.tfvars`. Choose a stable logical collector alias (no host identity) and set the required `alert_limits` object below. Keep `alerts_enabled=false` and `monitoring_enrolled=false` for initial provisioning. Notification-channel names are optional while disabled; destinations stay private and out of PRs.
3. Use an existing private operator-controlled GCS backend with versioning/locking and a distinct `capture/` prefix if configured. Copy `backend.tf.example` to ignored `backend.tf` only during the reviewed backend setup, then supply bucket/prefix privately at init. Do not use the landing bucket for state, grant the collector state access, or share a prefix with CD/serving. If starting with local state, keep one operator and make protected pre/post-apply backups with hashes, preserving the previous backup. Do not run concurrent applies.
4. Before a real plan, choose values privately for every field; the root intentionally supplies no production defaults:

| `alert_limits` field | Unit / requirement |
| --- | --- |
| `absence_seconds` | Whole-minute heartbeat gap within Monitoring's supported window |
| `sustained_seconds` | Whole-minute duration for health/unknown/capacity violations |
| `capture_age_seconds` | Map containing `vehicle-positions`, `trip-updates`, `service-alerts`, each an integer age in seconds |
| `upload_age_seconds` | Integer limit for last confirmed upload and oldest required unconfirmed upload |
| `free_bytes` | Integer warning level above the actual configured byte reserve plus capture allowance |
| `free_inodes` | Integer warning level above the actual configured inode reserve plus capture allowance |

Validation checks capacity warnings against the shipped default hard stop; if the host increases its reserves, compare the plan with that private host configuration too. These are operational alert thresholds, not product freshness or animation policy. Measure normal scheduling, exporter latency and upload behavior before accepting them.

Save and privately inspect a concrete plan:

```powershell
terraform -chdir=infra/capture plan "-out=capture.tfplan"
terraform -chdir=infra/capture show -no-color capture.tfplan
```

Stop for unexpected changes/replacements, broader grants, enabled alerts or public access. Present the exact plan for architect approval; **merge does not authorize apply**. Apply only the approved saved file (`terraform -chdir=infra/capture apply capture.tfplan`). Never regenerate a plan silently between review and apply. State/plan output contains private aliases, notification references and thresholds even though no private key is generated; do not publish it.

## IAM and storage acceptance

After separately approved apply:

- Read back bucket location, public-access prevention, uniform IAM, soft-delete protection and absence of automatic deletion. Compare effective inherited grants as well as this root's bindings. `objectCreator` plus the custom get role should be the only landing access for the collector; its only project grant from this root is the custom time-series write role.
- Verify the custom roles contain exactly `storage.objects.get` and `monitoring.timeSeries.create`, respectively. The latter is deliberately project-scoped; it does not enforce the metric namespace. Notification channels are operator-owned existing resources, not editable by the collector.
- Create the JSON key only through the approved operator procedure after encrypted-host acceptance; keep it on the encrypted volume with restrictive permissions. Never copy the key into Terraform, an image, a CLI argument or a public artifact. Use separately supplied short-lived test credentials or that approved identity for permission tests; do not print access tokens.
- Upload a bounded synthetic normalized test object with single-request checksums and `ifGenerationMatch=0`; prove known-name metadata get works and compare generation, server CRC32C/MD5 and size. Repeat the create to obtain 412 and reconcile it without `alt=media`. Prove object list, overwrite and delete are denied, using only isolated test objects for destructive-denial probes. An operator removes test objects afterwards. A mocked IAM plan does not establish these results.
- Prove the identity can write an expected Monitoring point while alert/channel administration and unrelated Storage access are denied. Do not add broader permissions to overcome a failure without review. A time-series-only role has no general metric-descriptor administration; descriptors are installed by Terraform before the exporter uses them.

## Monitoring enrollment and loss drill

The current [continuous collector](collector-continuous.md) has only a local dry-run sink. The authenticated exporter and durable upload-derived metrics must be integrated and tested before setting `monitoring_enrolled=true`.

Use Terraform's `metric_types` and `monitored_resource` outputs as the wire schema. Resource labels are `project_id`, Melbourne location, namespace `urbanpulse`, job `capture`, and the stable collector alias. Capture age/known metrics have exactly three feed labels. Do not add process IDs, session IDs, object names, hostnames or provider keys as labels. Emit live measurements on the collection loop's bounded pulse cadence; no replay or fixture point may impersonate current live health. Export failures must not change capture outcomes.

Age comes from durable capture completion/upload confirmation, not the last attempted HTTP request. When a timestamp is unknown, emit `*_success_known=0` and omit its age. An empty authoritative upload queue is pending age 0; an unavailable queue is unknown, not empty. If a clock is invalid or backwards, do not fabricate a fresh success or submit future points. Preserve state across restart; keep the logical alias stable. The [Monitoring API](https://docs.cloud.google.com/monitoring/api/ref_v3/rest/v3/projects.timeSeries/create) requires newer point timestamps for each series and reports partial-write failures; check every response.

Enrollment requires a private inventory of all expected streams, actual point arrival and a verified notification channel. Establish truthful success/age and pending-queue measurements through bounded accepted capture/upload tests; do not manufacture successes to seed them. Initial unknown-state metrics must also be exercised. [Metric absence cannot detect a never-created series](https://docs.cloud.google.com/monitoring/alerts/metric-absence); a Terraform flag alone is not proof of coverage.

Then review a second saved plan enabling policies with chosen channel names and `monitoring_enrolled=true`. After apply, verify fresh points again, because a policy update can reset evaluation. Run controlled tests and record arrival, detection, notification and recovery times privately:

1. Stop heartbeat/export delivery, including host-offline/locked-volume simulation. Confirm the external notification, then genuine recovery on resume.
2. Keep heartbeat running while one feed has no further successful captures. Confirm that feed's age/unknown policy fires; other feeds must not hide it.
3. Keep unrelated uploads succeeding while one required object remains pending. Confirm pending-age notification; test no confirmed upload/unknown history separately.
4. Cross byte and inode warning thresholds on a disposable fixture filesystem. Confirm alerts arrive before the actual collector hard stop, then explicit operator restart after capacity repair. Do not fill the real disk.
5. Stop one health metric while heartbeat continues. Confirm missing established data is treated as failure. Separately test startup with no samples; enrollment must refuse to claim coverage until every expected stream is accounted for.

Planned maintenance is still a gap. Monitoring may auto-close an incident after prolonged missing data; closure alone is not recovery. Check new points and source/upload progress. Changing metric/resource labels or policy configuration requires re-enrollment/loss testing; record the matching image and commit.

## Remaining rollout gates

This root deliberately has no object deletion rule. The accepted 12-month normalized-history policy still needs an implementation that preserves referenced manifests/static data and records expiry; raw-duration selection and the local expiry writer are separate. Upload confirmation, exporter/client wiring, actual IAM denial evidence, encrypted-host provisioning, notification delivery and bounded live acceptance remain required before unattended capture. Progress lives in the [delivery plan](../delivery-plan.md).

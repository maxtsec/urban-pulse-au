# Compose smoke: complete project cleanup

Date: 5 October 2026. Reproduce with `python -O scripts/compose_smoke.py`; see the [development guide](../development.md#isolated-smoke-cleanup).

The previous teardown enabled only the app profile. Stopped `recovery-worker` and `city-worker` containers remained outside that selected service graph, even when Compose reported a successful `down`. Earlier evidence describing complete stack removal was too broad.

Cleanup now enables all profiles for the generated smoke project, then queries containers (including stopped ones), networks and volumes by its exact Compose project label. Any remaining resource or inspection failure prevents a successful cleanup report. A pre-existing smoke failure remains the primary error, with cleanup failure attached. The cleanup guard rejects project names outside the generated smoke naming scheme.

## Verification

- Ruff lint/format passed. The full local unit/API suite passed **436 tests**; its 19 cleanup/smoke cases cover all-profile teardown, each residual resource type, invalid project scope and preservation of an earlier failure. The normal 142 PostGIS integration tests are excluded from that unit command; CI runs them separately.
- The real Docker rehearsal passed under optimized Python, including initialization, API recreation, proxy, durable checkpoints, replay, database restart and optional cache modes. Post-teardown queries found **zero containers, networks and volumes** for its project, including both inactive worker profiles.
- Historical local cleanup verified project/service/configuration labels and exited state before removing **19 stopped workers across 10 old smoke projects**. No matching networks or volumes remained; other containers present before this cleanup remained afterwards. The audit log is local under `.local/compose-smoke/historical-cleanup.log` in the verification checkout.

Normal development resources are not cleanup targets. Logs and evidence files are retained; this change concerns Compose resources and does not prune shared images or build caches. CI runs the same end-of-smoke absence checks.

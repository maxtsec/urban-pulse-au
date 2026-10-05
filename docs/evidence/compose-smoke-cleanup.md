# Compose smoke: complete project cleanup

Date: 6 October 2026. Reproduce with `python -O scripts/compose_smoke.py`; see the [development guide](../development.md#isolated-smoke-cleanup).

The previous teardown enabled only the app profile. Stopped `recovery-worker` and `city-worker` containers remained outside that selected service graph, even when Compose reported a successful `down`. Earlier evidence describing complete stack removal was too broad.

Cleanup enables all profiles for the generated smoke project, then queries containers (including stopped ones), networks and volumes by its exact Compose project label. Redis removal during the cache transition uses `rm -f -v redis`: without `-v`, its image-declared anonymous volume survives after its container disappears and has no project label.

The smoke also records volume mounts from project containers before each `up`/`rm` and before final teardown. It checks every recorded name against the remaining volume inventory, including anonymous volumes whose original containers have gone. Unrelated volumes are not removal targets. Inspection failure still attempts teardown but prevents a successful cleanup report; a pre-existing smoke failure remains the primary error. The cleanup guard rejects project names outside the generated smoke naming scheme.

## Verification

- Ruff lint/format passed. The full local unit/API suite passed **455 tests**; its 26 cleanup/smoke cases cover all-profile teardown, each residual resource type, invalid project scope, anonymous mounts after container removal, unrelated-volume preservation, inventory failure and preservation of an earlier failure. The normal 142 PostGIS integration tests are excluded from that unit command; CI runs them separately.
- The real Docker rehearsal passed under optimized Python, including initialization, API recreation, proxy, durable checkpoints, replay, database restart and optional cache modes. Post-teardown checks found **zero project-labelled resources and zero recorded volume mounts**, including both inactive worker profiles and Redis anonymous storage. An independent inventory of all Docker volume names before and after the run found **zero added and zero removed volumes**. The local run was `urbanpulse-smoke-228ee30918d2`.
- Historical local cleanup verified project/service/configuration labels and exited state before removing **19 stopped workers across 10 old smoke projects**. No project-labelled networks or volumes remained; that historical audit did not establish absence of unlabelled anonymous volumes. Other containers present before this cleanup remained afterwards. The audit log is local under `.local/compose-smoke/historical-cleanup.log` in the verification checkout.

Normal development resources are not cleanup targets. Logs and evidence files are retained; this change concerns Compose resources and does not prune shared images or build caches. CI runs the same end-of-smoke absence checks.

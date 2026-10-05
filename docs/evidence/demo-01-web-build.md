# DEMO-01: Static web packaging

Date: 5 October 2026. Reproduce using [development instructions](../development.md#static-web-packaging-for-the-demo). Progress belongs in the [delivery plan](../delivery-plan.md).

The provider-independent web build exports compiled Vite assets through a scratch `assets` target. The final/default Docker target remains `development`, retaining the existing Compose behavior. The deployment server and cloud choices remain in [PR #19](https://github.com/maxtsec/urban-pulse-au/pull/19).

## Verification

- `python -O scripts/web_build_smoke.py` passed with the real Docker builder. Fourteen synthetic probes covered root/nested environment files, npm credentials, keys, agent instructions and local/Git directories. They were absent from the source-containing build stage, not merely omitted from the exported site.
- The exported index references compiled assets; JavaScript is present; source, dependency directories, package metadata and probe paths are absent. No Vite development entrypoint/client is referenced.
- The smoke owns a unique image tag and removes it without replacing an earlier failure. The generated context contains tracked source plus synthetic probes; actual private workstation files are not copied. Logs and static output remain local.
- `python -O scripts/compose_smoke.py` passed: cold readiness, initialization, API/city/evidence and UI proxy, API recreation, durable expiry, worker replay and database restart recovery. Its isolated stack and volume were removed. Ruff lint/format and documentation link checks also passed.

CI runs the same packaging probe before the existing Compose smoke and retains the Docker log. The initial packaging check does not certify HTTP caching, browser behavior on a hosted server, HTTPS, registry manifest digests, base-image pinning, deployment identity or rollback. Those remain later DEMO-01 acceptance steps after architecture review.

# DEMO-01: Static web packaging

Date: 5 October 2026. Reproduce using [development instructions](../development.md#static-web-packaging-for-the-demo). Progress belongs in the [delivery plan](../delivery-plan.md).

The provider-independent web build exports compiled Vite assets through a scratch `assets` target. The final/default Docker target remains `development`, retaining the existing Compose behavior. Managed hosting and IAP are accepted in [ADR 0010](../adr/0010-hosted-fixture-demo.md); this slice verifies packaging.

## Verification

- `python -O scripts/web_build_smoke.py` passed with the real Docker builder. The adversarial context covers root/nested environment files, npm credentials, JSON service credentials, P12/key files, `id_rsa`, Playwright traces/screenshots, agent instructions and unknown source/asset files. Exact source-entry inventories passed for both that context and the actual local web context, including local untracked files handled by Docker. Generated dependency/build directory contents are excluded from source enumeration; the static export is checked separately.
- The exported index references compiled assets; JavaScript is present; source, dependency directories, package metadata and probe paths are absent. No Vite development entrypoint/client is referenced.
- The smoke owns a unique image tag and removes it without replacing an earlier failure. The adversarial context uses tracked working-tree source plus fake probes; Docker then builds the actual web context through the verified allowlist. Logs, both inventories and static output remain local. Nine unit regressions verify unknown entries, required inputs and unstaged deletion handling.
- `python -O scripts/compose_smoke.py` passed: cold readiness, initialization, API/city/evidence and UI proxy, API recreation, durable expiry, worker replay and database restart recovery. Its isolated stack and volume were removed. Ruff lint/format and documentation link checks also passed.

CI runs both packaging contexts before the existing Compose smoke and retains the Docker log and source-entry inventories. The initial packaging check does not certify HTTP caching, browser behavior on a hosted server, HTTPS, registry manifest digests, base-image pinning, deployment identity or rollback. Those remain later DEMO-01 implementation and acceptance steps under ADR 0010.

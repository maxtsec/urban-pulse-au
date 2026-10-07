# CLOUD-01 v3 store validation

Date: 2026-10-07

The [v3 format](../architecture/capture-store-v3.md) adds an explicit fresh-store marker, independent normalization/upload records and expiry-aware verification. This evidence covers local fixture behavior, not source permission, target-host encryption, cloud IAM or live operation.

Validation results: 755 local unit tests passed (175 Linux-only tests skipped; 190 integration tests excluded); the isolated Linux suite passed 211 tests. Ruff lint/format and mypy (81 source files) passed. No database/API runtime behavior changed.

## Automated coverage

- V2/v3 marker isolation, original v2 recovery regressions and initialization crash refusal.
- Process termination during capture publication, scope publication, pending/normalization/confirmation publication, cursor replacement and verification.
- Contiguous cursor advancement, immutable conflict refusal, duplicate recovery, verification holds and no idle history enumeration.
- Valid expired provenance, missing payload without expiry, incomplete expiry with raw either present or absent, mismatched policy/scope/checksums, missing records, outstanding upload pins and symlink/cursor corruption.
- Real CLI selection in an isolated Linux process, plus bounded cross-platform record validation.

Synthetic expiry records are created by test helpers only. Tests deliberately remove synthetic payloads to exercise the reader. There is no production expiry writer or delete command; future unlink/fsync crash tests remain part of the expiry-execution PR. Process termination does not certify physical disk power-loss durability.

Reproduce the isolated Linux suite from the repository root:

```powershell
docker build --target test -f workers/capture/Dockerfile -t urbanpulse-capture:v3-test .
docker run --rm --network none --read-only --tmpfs /tmp:rw,nosuid,nodev,size=512m --cap-drop ALL --security-opt no-new-privileges --pids-limit 128 --memory 512m urbanpulse-capture:v3-test
```

Tests explicitly inject a test-only filesystem check for the disposable tmpfs. Production filesystem checks and CLI defaults remain intact; helper files are absent from the runtime target.

## Runtime boundary check

The unmodified `runtime` image was additionally run without network access, as its non-root user, with a read-only root filesystem, dropped capabilities and a newly created persistent Docker volume. `init`, a three-attempt fixture `run`, `status` and `verify`, all with `--store-version v3`, succeeded. Verify counted three captures, 112 retained payload bytes and no expired payloads. The same volume was rejected by default v2 `status`. The disposable volume was removed afterwards.

To repeat, use the hardened runtime invocation in the [local capture runbook](../runbooks/local-capture.md#explicit-v3-fixture-rehearsal) with a new persistent store. Do not reuse or relabel a v2 archive. The Ubuntu collector host was not changed for these checks.

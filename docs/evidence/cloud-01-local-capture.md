# CLOUD-01 local capture acceptance

The local recovery format is accepted in [ADR 0016](../adr/0016-local-capture-recovery.md). [Runbook](../runbooks/local-capture.md) contains executable Ubuntu and Linux test commands; [delivery plan](../delivery-plan.md) owns progress.

## Scope and method

All requests in this acceptance use synthetic bytes or HTTP mocks. No provider key is read, live source enabled or cloud resource created. The journal and CLI execute inside a Linux container as UID 10001 with a read-only root filesystem, no network and dropped capabilities. Test-only injection permits disposable tmpfs for recovery cases; unmodified CLI tests reject ephemeral storage. The runtime-image round trip uses a persistent Docker volume.

| Case | Observed result |
| --- | --- |
| Repeated identical response | Separate UUID captures, identical SHA-256, exact retained bytes |
| Repeat storage completion | Existing manifest returned unchanged; conflicting bytes rejected |
| Child exits after directory/intent/payload/receipt staging | Pre-intent orphan preserved or attempt abandoned; no fabricated receipt |
| Child exits after response publication or manifest | Complete response verified and manifest recovered or unchanged |
| Second process and killed owner | Second writer refused; OS lock released after owner termination |
| Missing store/marker, unknown directory, corrupt evidence | Collection refused; evidence preserved |
| Low disk and write failure | No request admitted below reserve; raw failure recorded if possible; published response remains recoverable |
| Runtime filesystem policy | Real tmpfs and overlay init rejected; unmodified init/run/status rejected on tmpfs; no runtime bypass |
| Failure after HTTP 200 | Mocked interrupted stream, elapsed timeout, size limit and encoding error each back off, allocate a new capture ID and successfully retry |
| HTTP errors and request budget | Fixed redacted outcomes, no redirects, bounded size/time, Retry-After and retry budget tested |
| Restart after rate limiting | Persisted Retry-After deadline retained |
| CLI fixture run/status/SIGTERM | Finite capture lifecycle tested through real entry point; controlled stop releases ownership |

## Validation

Local Windows unit suite: 670 passed, 31 Linux-only tests skipped, 182 integration tests deselected. Ruff lint/format and mypy (73 source files) passed. Linux collector container: 61 tests passed, including the 31 filesystem/process cases skipped on Windows. Test commands are in the runbook and the project checks workflow. The runtime image also completed init, two six-attempt fixture runs in separate containers, and status verification over one disposable persistent Docker volume: 12 retained captures, zero failures. The volume was removed afterwards.

This does not establish live cadence/retention permission, physical power-loss safety, actual Ubuntu host installation, sustained disk growth, cloud upload confirmation or external heartbeat delivery. Those checks remain in CLOUD-01/SRC-02. The source probe's independent provider evidence remains in [SRC-02](src-02-transport-probe.md).

## V1 image reduction and startup limit

The same local Docker Engine reports `docker image inspect urbanpulse-capture:local --format '{{.Size}}'` decreasing from 677,051,690 to 201,789,670 bytes (approximately 646 to 192 MiB). This is the local image size, not compressed registry transfer bytes. The runtime contains only the eleven distributions required by httpx/pydantic. Inspection confirmed no uv executable, pytest, FastAPI, polars, Google Cloud packages or test helper in the runtime image; the existing pinned Python base is unchanged.

In this v1 acceptance, run/status enumerate every capture and hash every successful payload. The architect deferred this finding to a mandatory live-activation gate: a durable pending index, incomplete-only restart reconciliation, a separate full verify command and measured restart cost. Fixture crash acceptance does not close that scalability gate.

The subsequent [v2 checkpoint evidence](cloud-01-incremental-recovery.md) records the implementation of ADR 0017 and separate offline verification.

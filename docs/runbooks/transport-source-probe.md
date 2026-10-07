# Transport source probe

Use this operator-run research tool for SRC-02 before building a continuous collector. It writes only under ignored `.local/src-02-transport/`, sends no data to GCP and does not update the application or its database. Source enablement still follows the [source register](../source-register.md) and [ADR 0015](../adr/0015-local-capture-collector.md).

## Prepare

From the repository root, restore development dependencies with `uv sync --locked`. The official GTFS-Realtime bindings are a development-only dependency. Put `DTP_OPENDATA_API_KEY` in the ignored `.env`, or supply it through the local environment. Do not print it or paste it into command arguments. Environment values take precedence over `.env`.

Download the [official GTFS Schedule archive](https://opendata.transport.vic.gov.au/dataset/gtfs-schedule) under `.local/`. Record its download URL, time, SHA-256 and available publication metadata privately. Extract only the inner `3/google_transit.zip` as `.local/map-02-source/tram.zip`; do not pass the statewide outer archive to the tool. The [measured evidence](../evidence/src-02-transport-probe.md) identifies the archive used for this PR; future schedules require new hashes and results.

Offline inspection makes no network requests and needs no credential:

```powershell
uv run --locked python -m scripts.transport_probe --static-zip .local/map-02-source/tram.zip
```

## Bounded live run

Ensure no other collector/probe is using this subscription. The local lock only coordinates this checkout's research runs, not other hosts, applications or subscription users. It is not the CLOUD-01 production lease.

```powershell
uv run --locked python -m scripts.transport_probe --static-zip .local/map-02-source/tram.zip --live --duration-seconds 120
```

The default is offline. With `--live`, the default 60-second sampling horizon makes at most seven requests over 80 seconds; 120 makes at most eleven over 140 seconds because updates/alerts are staggered after the last positions sample. Sequential requests are at least ten seconds apart. Slow responses cannot trigger catch-up bursts; an overall scheduling deadline stops unfinished runs. Requests have a ten-second I/O timeout and an additional elapsed check while receiving chunks. This is a bounded probe, not a hard real-time watchdog.

Each body is capped at 8 MiB; only identity content encoding is retained. ZIP members are capped at 128 MiB and the local static ZIP at 256 MiB. Redirects are not followed. Any HTTP failure, including authentication failure or 429, stops the run without retrying. Fix the cause before an independently reviewed rerun; do not use this tool to find the provider's rate-limit ceiling.

`KeyID` is the working header measured for the current subscription. `--header Ocp-Apim-Subscription-Key` permits an explicit comparison with the contradictory OpenAPI documentation; a failed first request stops the run. No automated credential spraying or header fallback occurs.

## Inspect and retain evidence

The printed result names a unique private directory. Each successful HTTP body is saved as `.pb`, including a malformed protobuf that is then rejected; the JSON report contains capture times, sizes, hashes, missing-field/linkage counts and consecutive-position comparisons. HTTP error bodies and exception strings are not retained. A successful HTTP response alone is not a valid GTFS capture.

Raw payload equality includes the header. `unchanged_entities` ignores header changes and entity ordering using a diagnostic fingerprint; neither measure substitutes for production event identity. `linked` only verifies exact static references and service date, not physical shape matching. Reports do not infer current coverage from an empty feed or from the FULL_DATASET flag.

Recheck retained payload hashes before offline analysis. Decode them using `scripts.gtfs_probe.decode`, recompute `summarize` with the **original** report receipt timestamp and the identical static archive, and use `entity_fingerprint` for header-independent comparison. This needs no further live requests. The first run's subsequent entity/motion analysis is retained separately as `analysis.json`, preserving its original `report.json`.

Keep keys, raw source bytes and detailed local reports out of commits. Publish only reviewed aggregate evidence and provenance hashes. These samples have no automated deletion policy; review their local retention with SRC-02. If interrupted, retain the partial directory; check that no process owns `probe.lock` before removing that exact stale file. Do not restart repeatedly to bypass the request budget.

## Acceptance boundary

The probe tests authentication and a small sample of source behavior. It does not establish account-wide quota, complete source coverage, production TTL, the upload acknowledgement protocol or a capture lease. Those remain CLOUD-01/source-policy gates. Normal application and CI tests use synthetic data and never require the provider credential.

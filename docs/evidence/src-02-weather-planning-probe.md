# SRC-02: Bounded weather and development reads

Measured 8 October 2026 using [the replayable probe](../../scripts/source_probe.py). This is an access/schema sample, not permission for continuous weather/planning capture or a live UI. See the [source register](../source-register.md) for remaining source-use decisions.

## Scope and reproduction

The run made ten public GET requests, retained 100,056 response bytes and made no provider writes, key use, production imports or database changes. One earlier DAM metadata preflight made an additional GET outside this retained run. The source commit was `c763401f2b84e659e569eb31740f85b8a4093190`, with `dirty=true`; the exact probe script SHA-256 was `6adcd78e62d313ef403361873d1c0ebf543778ed95ea7cb38c51fb7030a4ac46`. Responses and receipt timestamps are retained in private operator evidence, with the hashes below; they are not packaged into the public UI.

```powershell
uv run --locked python -m scripts.source_probe --capture .local/source-probe/new-run
uv run --locked python -m scripts.source_probe --replay .local/source-probe/new-run
```

Use a new output directory for each capture. Replay requires the retained manifest and response files and makes no network requests. The probe limits each run to 24 requests (two metadata reads, two weather reads and up to ten DAM pages per area), 2 MiB per response, a 180-second elapsed budget checked around reads, a 15-second HTTP timeout and 1,000 DAM rows per area. It never follows redirects or retries failed requests. Partial/failed runs remain diagnostic; replay refuses an unfinished manifest. Stored hashes are checked before analysis. Pagination limits or duplicate identities prevent a complete-page result. Stable dataset metadata across requests does not establish transactional source-snapshot isolation.

## Weather

Two representative query points were Southbank (-37.825, 144.963) and CBD (-37.814, 144.963). Current-only requests selected `best_match`, UTC epoch seconds, temperature, precipitation, rain, WMO weather code, cloud cover, wind speed and day/night. No hourly/daily forecast series was requested.

Both returned effective time **2026-10-08 04:45 UTC** with a 900-second interval, 21.6 °C, no modelled rain/precipitation, weather code 0, cloud cover 0%, wind 4.45 m/s and daytime. All requested values were present. Both resolved to the same reported grid coordinates (-37.785587, 144.93976), with different returned elevation values. These are model estimates, not street/station measurements or evidence of two independent area conditions. The response does not name the resolved model behind `best_match`; retain the request policy and leave that identity unknown rather than inventing it.

[Open-Meteo documentation](https://open-meteo.com/en/docs) describes current values as modelled 15-minute data. Its [terms](https://open-meteo.com/en/terms) separate non-commercial API access from CC BY 4.0 data licensing. This private development probe is bounded; public/portfolio deployment eligibility, attribution, cadence, retention, missing/stale behavior and any sunny/cloudy/rainy mapping remain explicit decisions before serving. Fog, snow and thunderstorm codes must not silently become sunny. Modelled readings do not satisfy weather-warning coverage; VicEmergency/BOM warning gates are unchanged.

## Development Activity Monitor

[DAM metadata and schema](https://data.melbourne.vic.gov.au/api/explore/v2.1/catalog/datasets/development-activity-monitor) reported monthly updates, CC BY 4.0 and dataset modification/processing at **2026-09-24 05:11:36 UTC**. Before/after metadata was stable. Queries selected original development identity, status, CLUE label, point and completion-year fields, ordered by identity and paged in batches of 100.

| Provider area label | Records / unique keys | APPLIED | APPROVED | UNDER CONSTRUCTION | COMPLETED | Missing points |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Southbank | 128 / 128 | 7 | 29 | 5 | 87 | 0 |
| Melbourne (CBD) | 335 / 335 | 7 | 49 | 11 | 268 | 0 |

Retrieved counts equal the provider totals and identities are unique in each area. These counts use provider CLUE labels; this probe does not repeat the PostGIS boundary check. Dataset publication time is not a per-record change time or on-site observation. DAM covers major developments, not every road closure, small construction activity or crane location. Keep source statuses and dates, and do not infer a health penalty from development volume. Continuous capture cadence/retention, spatial validation and lifecycle integration remain source enablement work.

Attribution: modelled weather data by Open-Meteo, CC BY 4.0; development records by City of Melbourne, CC BY 4.0. This report filters and aggregates the selected areas and preserves original status labels.

## Retained response hashes

| Capture | Bytes | SHA-256 |
| --- | ---: | --- |
| dam-before | 9632 | `2cd7a0c3a462129a9aa531847a15d9d1313f02fd751edc94b04338145f00f355` |
| weather-0 | 528 | `062caeada109de98836a533b75ea28f971e07c7310fd1db4cf70c4b006946ce3` |
| dam-0-0 | 16767 | `9e82915ca86053e4984a5efc5dd08ba4c7fd5d1b749a27e26b97522ad31a867e` |
| dam-0-100 | 4685 | `efec178c82af0facc1c0918551b8786c61d3c2ad80735d3b8139681bb7b01079` |
| weather-1 | 530 | `31f46434483111771870a804dd51722597c1f338dc642c001351c4b6ff385ed1` |
| dam-1-0 | 17415 | `7061318ed58117d9dd1337e4a40d06912f2e95619e266cb21f6d9bce4b5dd384` |
| dam-1-100 | 17404 | `7e5dff55ba6d9dbacb440b21c1ec71f8034ad34b87447247c450cce86c6515f8` |
| dam-1-200 | 17341 | `37b0eee3fc3ab5279822c67abae6a4cb1c5ce604ee69aada71e459c524e2f07a` |
| dam-1-300 | 6122 | `eb287b17813bb699b2ff1ce25f6a944c0013571b71059bc28e44c75d527306ef` |
| dam-after | 9632 | `2cd7a0c3a462129a9aa531847a15d9d1313f02fd751edc94b04338145f00f355` |

## Verification

Offline tests cover pagination/replay, missing values and positions, duplicate/incomplete rows, wrong area/units/time, malformed data, payload tampering, unsafe capture references, redirects/errors without retry, response/request/time bounds. Probe code is included in strict mypy and the existing test suite. Validation: Ruff lint/format, strict mypy (85 files), six focused probe tests and the full Windows unit run passed (876 passed, 181 platform skips, 190 integration deselections). Offline replay exactly matched the retained analysis, its script hash matched the capture, and 919 local documentation links resolved. No Weather/DAM scheduled collector or public view was enabled by the probe.

The request ceiling was raised from 16 to 24 after review; this does not change the ten-request retained run above. A regression exercises both areas at 1,000 rows, and an advertised 1,001 rows remains explicitly incomplete after the ten-page bound. The elapsed-time and response-size limits remain independent fail-safe bounds.

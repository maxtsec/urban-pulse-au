# MAP-02 animation payload estimate

Measured: 7 October 2026 for the [accepted animation input contract](../architecture/tram-animation-input-contract.md). B uses a separate same-origin endpoint; 2D does not request this payload. This is an encoding estimate, not a real GTFS fixture, valid playback window, HTTP benchmark or implementation claim.

The comparison retains the same unique 64-character event/capture/continuity IDs, coordinates, one capture reference per observation and matching metadata. The former repeated representation places trip/shape fields on each observation. The accepted table representation stores those seven fields once per vehicle/continuity segment and keeps `{status, continuity_id, distance_m}` per observation. Both include scope/clock alignment; the new representation also includes `window_start` for animation-only continuations. Shapes are referenced, not embedded. Byte counts include the entire animation response, without surrounding area data.

| Vehicles | Samples each | Segments each | Repeated JSON | Repeated gzip | Table JSON | Table gzip | JSON saving |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 3 | 1 | 2,885 | 988 | 2,651 | 1,001 | 8.1% |
| 10 | 3 | 1 | 22,955 | 4,132 | 20,273 | 4,153 | 11.7% |
| 100 | 3 | 1 | 223,637 | 34,746 | 196,475 | 35,163 | 12.1% |
| 100 | 8 | 1 | 551,137 | 84,914 | 435,475 | 85,212 | 21.0% |
| 100 | 8 | 8 | 551,137 | 115,626 | 607,675 | 119,709 | -10.3% |

The table saves repeated metadata only when observations share a segment. Frequent trip/shape breaks reduce or reverse that benefit because each table entry still has a key and delimiters. These measurements replace the estimated 30–40% saving; do not claim a fixed compression benefit. Gzip sizes are slightly larger for the shared-segment cases here, so the measured benefit is smaller uncompressed JSON, not smaller compressed transfer. Original 6 October evidence measured 222,925 bytes for the 100×3 embedded A object (223,037 for B with alignment); the new comparison adds trip-segment suffixes to exercise shared and fragmented histories, so its baseline differs slightly.

The accepted 256 KiB uncompressed limit is 262,144 bytes. Segment tables do not make every eight-sample/100-vehicle response fit. Enforce the cap after compact UTF-8 serialization, including alignment, segment entries and metadata. Shorten only animation `window_end`, never parent `valid_until`; do not omit required observations or discontinuities. If even the requested instant cannot fit, return labelled static fallback via `unavailable/window_limit`. Each continuation retains the parent scope/clock and requests only animation.

Gzip uses level 6 with deterministic headers; it estimates transfer compression, not parsing/allocation costs or verified HTTP encoding. Longer IDs, multiple capture references and UTF-8 text can increase size. Parent data, shared freshness/validity fields, HTTP headers, model/shape assets and request latency are excluded. Repeat measurements with the retained animation fixture and actual HTTP encoding during implementation.

## Reproduce

Run the standard-library Python script below. Timestamps vary for sizing; the stress cases do not constitute valid replay windows. No runtime source or test files are needed for this documentation measurement.

```python
import gzip
import hashlib
import json
from datetime import datetime, timedelta, timezone

source = "urn:urbanpulse:fixture:transport"
base = datetime(2026, 10, 4, tzinfo=timezone.utc)


def timestamp(seconds):
    return (base + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def identity(value):
    return hashlib.sha256(value.encode()).hexdigest()


def payload(vehicle_count, samples, segments):
    vehicles = []
    for vehicle in range(vehicle_count):
        observations = []
        for sample in range(samples):
            key = f"vehicle-{vehicle}-sample-{sample}"
            observations.append(
                {
                    "source": source,
                    "event_id": identity(key),
                    "revision": sample + 1,
                    "capture_ids": [identity("capture-" + key)],
                    "observed_at": timestamp(sample * 30),
                    "received_at": timestamp(sample * 30 + 1),
                    "longitude": round(144.95 + vehicle * 0.0001 + sample * 0.00001, 6),
                    "latitude": round(-37.82 - vehicle * 0.0001 - sample * 0.00001, 6),
                    "shape_match": {
                        "status": "matched",
                        "trip_id": f"synthetic-trip-{vehicle:04d}-{sample * segments // samples}",
                        "service_date": "20261004",
                        "start_time": "11:00:00",
                        "route_id": "96",
                        "direction_id": 0,
                        "shape_id": f"synthetic-shape-{vehicle % 10:02d}",
                        "segment_id": "southbank-01",
                        "continuity_id": identity(
                            f"segment-{vehicle}-{sample * segments // samples}"
                        ),
                        "distance_m": 1200.25 + sample * 143.17,
                    },
                }
            )
        vehicles.append(
            {
                "vehicle_id": f"synthetic-vehicle-{vehicle:04d}",
                "source": source,
                "latest_observation": {"source": source, "event_id": observations[-1]["event_id"]},
                "startup_observation": None,
                "observations": observations,
            }
        )
    return {
        "contract_version": "tram-animation-input-v1",
        "display_policy_version": "tram-display-delay-v1",
        "status": "ready",
        "reason": None,
        "window_end": timestamp(90),
        "position_input": {
            "state": "available",
            "received_at": timestamp(61),
            "capture_ids": [identity("latest-position-input")],
        },
        "shapes": {
            "revision": "synthetic-shapes-v1",
            "sha256": identity("shape-manifest"),
            "url": "/assets/shapes/" + identity("shape-manifest") + ".json",
        },
        "vehicles": vehicles,
    }


def encode(value):
    return json.dumps(value, separators=(",", ":"), allow_nan=False).encode("utf-8")


def segment_table(value):
    value = json.loads(json.dumps(value))
    value["window_start"] = value["clock_at"]
    for vehicle in value["vehicles"]:
        segments = {}
        for observation in vehicle["observations"]:
            match = observation["shape_match"]
            key = match["continuity_id"]
            metadata = {
                k: v for k, v in match.items() if k not in {"status", "continuity_id", "distance_m"}
            }
            if key in segments:
                assert segments[key] == metadata
            segments[key] = metadata
            observation["shape_match"] = {
                k: match[k] for k in ["status", "continuity_id", "distance_m"]
            }
        vehicle["segments"] = segments
    return value


print(
    "| Vehicles | Samples each | Segments each | Repeated JSON | Repeated gzip | Table JSON | Table gzip | JSON saving |"
)
print("| --- | --- | --- | --- | --- | --- | --- | --- |")
for vehicle_count, samples, segments in [
    (1, 3, 1),
    (10, 3, 1),
    (100, 3, 1),
    (100, 8, 1),
    (100, 8, 8),
]:
    value = payload(vehicle_count, samples, segments)
    value.update(scope_id=identity("timeline"), clock_at=timestamp(75))
    repeated = encode(value)
    shared = encode(segment_table(value))
    savings = 100 * (1 - len(shared) / len(repeated))
    print(
        f"| {vehicle_count} | {samples} | {segments} | {len(repeated):,} | {len(gzip.compress(repeated, compresslevel=6, mtime=0)):,} | {len(shared):,} | {len(gzip.compress(shared, compresslevel=6, mtime=0)):,} | {savings:.1f}% |"
    )
```

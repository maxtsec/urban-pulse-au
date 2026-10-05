# MAP-02 animation payload estimate

Measured: 6 October 2026, using the proposed [animation input contract](../architecture/tram-animation-input-contract.md). This estimates encoding size before choosing API placement. It is not a real GTFS sample, valid replay-window fixture, latency measurement or evidence that the runtime contract is implemented.

The generator below includes every proposed field, unique 64-character event/capture/continuity identifiers, one capture reference per observation, varying coordinates, and a full matched-trip record. It measures the animation object as compact UTF-8 JSON without whitespace; the enclosing area field name/delimiters are excluded. Shapes are referenced, not embedded. A adds these bytes to every area snapshot, including static 2D. B adds scope/clock fields to a separate response and, if approved, can avoid that request in static 2D.

| Vehicles | Samples each | A JSON bytes | A gzip bytes | B JSON bytes |
| --- | --- | --- | --- | --- |
| 1 | 3 | 2,767 | 924 | 2,879 |
| 10 | 3 | 22,783 | 4,062 | 22,895 |
| 100 | 3 | 222,925 | 34,665 | 223,037 |
| 100 | 8 | 549,425 | 84,829 | 549,537 |

The proposed 256 KiB uncompressed limit is 262,144 bytes. The dense 100-vehicle/eight-sample case exceeds it: it is a stress estimate, not an allowable response. The implementation must shorten the window without dropping required history, or return animation unavailable if no complete window fits. Longer provider IDs, extra capture references, source-state evidence and UTF-8 text can increase sizes; enforce the byte limit on the serialized result rather than assuming a sample count guarantees it.

Gzip uses level 6 and deterministic headers. It shows possible transfer compression only: actual HTTP content encoding still needs verification, and compressed size does not remove JSON parsing/allocation costs. Hashes vary to avoid an unrealistically compressible repeated identifier. The base city snapshot, HTTP headers, model/shape asset downloads and request latency are excluded. For B, the separate response contains the same animation body plus the alignment fields; its extra request overhead is not measured here.

A preserves ADR 0011's current request invariant at a measurable cost to 2D. B avoids that cost in 2D only if the architect approves changing the invariant. Neither is selected by this measurement alone. Repeat with the completed retained fixture and real HTTP encoding in MAP-02 before accepting a payload/performance budget.

## Reproduce

Run this standard-library Python script (Python 3.12.15 was used). The counts measure field encodings; timestamps deliberately vary for sizing and do not constitute a replay-valid scenario.

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

def payload(vehicle_count, samples):
    vehicles = []
    for vehicle in range(vehicle_count):
        observations = []
        for sample in range(samples):
            key = f"vehicle-{vehicle}-sample-{sample}"
            observations.append({
                "source": source,
                "event_id": identity(key),
                "revision": sample + 1,
                "capture_ids": [identity("capture-" + key)],
                "observed_at": timestamp(sample * 30),
                "received_at": timestamp(sample * 30 + 1),
                "longitude": round(144.95 + vehicle * 0.0001 + sample * 0.00001, 6),
                "latitude": round(-37.82 - vehicle * 0.0001 - sample * 0.00001, 6),
                "shape_match": {
                    "status": "matched", "trip_id": f"synthetic-trip-{vehicle:04d}",
                    "service_date": "20261004", "start_time": "11:00:00",
                    "route_id": "96", "direction_id": 0,
                    "shape_id": f"synthetic-shape-{vehicle % 10:02d}",
                    "segment_id": "southbank-01", "continuity_id": identity(f"segment-{vehicle}"),
                    "distance_m": 1200.25 + sample * 143.17,
                },
            })
        vehicles.append({
            "vehicle_id": f"synthetic-vehicle-{vehicle:04d}", "source": source,
            "latest_observation": {"source": source, "event_id": observations[-1]["event_id"]},
            "startup_observation": None, "observations": observations,
        })
    return {
        "contract_version": "tram-animation-input-v1",
        "display_policy_version": "tram-display-delay-v1",
        "status": "ready", "reason": None, "window_end": timestamp(90),
        "position_input": {"state": "available", "received_at": timestamp(61),
                           "capture_ids": [identity("latest-position-input")]},
        "shapes": {"revision": "synthetic-shapes-v1", "sha256": identity("shape-manifest"),
                   "url": "/assets/shapes/" + identity("shape-manifest") + ".json"},
        "vehicles": vehicles,
    }

print("| Vehicles | Samples each | A JSON bytes | A gzip bytes | B JSON bytes |")
print("| --- | --- | --- | --- | --- |")
for vehicle_count, samples in [(1, 3), (10, 3), (100, 3), (100, 8)]:
    value = payload(vehicle_count, samples)
    raw = json.dumps(value, separators=(",", ":"), allow_nan=False).encode("utf-8")
    compressed = gzip.compress(raw, compresslevel=6, mtime=0)
    value.update(scope_id=identity("timeline"), clock_at=timestamp(75))
    separate = json.dumps(value, separators=(",", ":"), allow_nan=False).encode("utf-8")
    print(f"| {vehicle_count} | {samples} | {len(raw):,} | {len(compressed):,} | {len(separate):,} |")
```

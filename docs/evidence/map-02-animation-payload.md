# MAP-02 animation payload estimate

Measured with **CPython 3.12.15 on Windows, zlib build/runtime 1.3.2**, gzip level 6 and `mtime=0`: 7 October 2026 for the [accepted animation input contract](../architecture/tram-animation-input-contract.md). B uses a separate same-origin endpoint; 2D does not request this payload. This is an encoding estimate, not a real GTFS fixture, valid playback window, HTTP benchmark or implementation claim.

The comparison retains the same unique 64-character event/capture/continuity IDs, coordinates, one capture reference per observation and matching metadata. The former repeated representation places trip/shape fields on each observation. The accepted table representation stores those seven fields once per vehicle/continuity segment and keeps `{status, continuity_id, distance_m}` per observation. Both use identical scope/clock alignment, `window_start`, per-vehicle status/reason and all other non-linkage fields. Only repeated trip/shape metadata versus a shared segment table differs; the script reconstructs and compares the original object to enforce this. Shapes are referenced, not embedded. Byte counts include the entire animation response, without surrounding area data.

| Vehicles | Samples each | Segments each | Repeated JSON | Repeated gzip | Table JSON | Table gzip | JSON saving |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 3 | 1 | 2,954 | 996 | 2,682 | 1,004 | 9.2% |
| 10 | 3 | 1 | 23,303 | 4,143 | 20,583 | 4,154 | 11.7% |
| 100 | 3 | 1 | 226,775 | 34,748 | 199,575 | 35,145 | 12.0% |
| 100 | 4 | 2 | 292,075 | 48,692 | 271,775 | 49,874 | 7.0% |
| 100 | 5 | 1 | 358,475 | 54,584 | 295,875 | 54,869 | 17.5% |
| 100 | 8 | 1 | 554,275 | 84,893 | 438,575 | 85,193 | 20.9% |
| 100 | 8 | 8 | 554,275 | 115,643 | 610,775 | 119,687 | -10.2% |

The table saves metadata only when observations share a segment. Frequent trip/shape breaks reduce or reverse that benefit because each table entry still has a key and delimiters. Gzip results are measured independently; smaller JSON does not imply smaller compressed transfer. These like-for-like measurements supersede the earlier unequal-envelope comparison, so compare values within this table rather than inferring an encoding change from old totals.

The accepted 256 KiB uncompressed limit is 262,144 bytes. Segment tables do not make every eight-sample/100-vehicle response fit. Enforce the cap after compact UTF-8 serialization, including alignment, segment entries and metadata. Shorten only animation `window_end`, never parent `valid_until`; do not omit required observations from ready vehicles. If the required instant already exceeds the cap, use deterministic per-vehicle admission and static stubs, preserving other vehicles. A response-wide failure is reserved for an envelope that cannot fit even with all vehicles static. Each continuation retains the parent scope/clock and requests only animation.

The four-sample/two-segment and five-sample cases already overflow before considering a longer window. The following encoding-only experiment treats each vehicle's shown history as required at one instant: reserve static stubs, then admit complete vehicle records in parent order. No ready record loses a sample. This demonstrates that overflow need not disable all 100 vehicles.

| Vehicles | Samples each | Segments each | Ready | Static | Bounded JSON |
| --- | --- | --- | --- | --- | --- |
| 100 | 3 | 1 | 100 | 0 | 199,575 |
| 100 | 4 | 2 | 96 | 4 | 261,427 |
| 100 | 5 | 1 | 88 | 12 | 261,941 |
| 100 | 8 | 8 | 41 | 59 | 258,142 |

The bounded experiment does not implement canonical city-interval admission, temporal window construction, unmatched metadata or startup-history validation. Runtime acceptance must additionally verify stable admission across seeks/continuations, one missing startup history among 99 healthy vehicles, and complete retained history at every rendered instant.

Gzip uses level 6 with deterministic headers; it estimates transfer compression, not parsing/allocation costs or verified HTTP encoding. Longer IDs, multiple capture references and UTF-8 text can increase size. Parent data, shared freshness/validity fields, HTTP headers, model/shape assets and request latency are excluded. Exact gzip bytes require the recorded Python/zlib environment; other versions may differ even with identical JSON. Repeat measurements with the retained animation fixture and actual HTTP encoding during implementation.

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
                "status": "ready",
                "reason": None,
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
    (100, 4, 2),
    (100, 5, 1),
    (100, 8, 1),
    (100, 8, 8),
]:
    value = payload(vehicle_count, samples, segments)
    value.update(scope_id=identity("timeline"), clock_at=timestamp(75), window_start=timestamp(75))
    table = segment_table(value)
    restored = json.loads(json.dumps(table))
    for vehicle in restored["vehicles"]:
        segments_by_id = vehicle.pop("segments")
        for observation in vehicle["observations"]:
            match = observation["shape_match"]
            match.update(segments_by_id[match["continuity_id"]])
    assert restored == value
    repeated = encode(value)
    shared = encode(table)
    savings = 100 * (1 - len(shared) / len(repeated))
    print(
        f"| {vehicle_count} | {samples} | {segments} | {len(repeated):,} | {len(gzip.compress(repeated, compresslevel=6, mtime=0)):,} | {len(shared):,} | {len(gzip.compress(shared, compresslevel=6, mtime=0)):,} | {savings:.1f}% |"
    )


def bounded(value):
    result = json.loads(json.dumps(value))
    result["vehicles"] = [
        {
            "vehicle_id": v["vehicle_id"],
            "source": v["source"],
            "status": "static",
            "reason": "byte_limit",
        }
        for v in value["vehicles"]
    ]
    if len(encode(result)) > 262144:
        raise ValueError("all-static envelope exceeds limit")
    for index, vehicle in enumerate(value["vehicles"]):
        stub = result["vehicles"][index]
        result["vehicles"][index] = vehicle
        if len(encode(result)) > 262144:
            result["vehicles"][index] = stub
    return result


print("| Vehicles | Samples each | Segments each | Ready | Static | Bounded JSON |")
print("| --- | --- | --- | --- | --- | --- |")
for count, samples, segments in [(100, 3, 1), (100, 4, 2), (100, 5, 1), (100, 8, 8)]:
    value = payload(count, samples, segments)
    value.update(scope_id=identity("timeline"), clock_at=timestamp(75), window_start=timestamp(75))
    original = segment_table(value)
    limited = bounded(original)
    ready = sum(v["status"] == "ready" for v in limited["vehicles"])
    assert len(limited["vehicles"]) == count
    assert 0 < ready <= count
    assert len(encode(limited)) <= 262144
    assert limited == bounded(original)
    for before, after in zip(original["vehicles"], limited["vehicles"], strict=True):
        assert after["status"] == "static" or after == before
    print(
        f"| {count} | {samples} | {segments} | {ready} | {count - ready} | {len(encode(limited)):,} |"
    )
```

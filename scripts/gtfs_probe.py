"""Offline, conservative GTFS linkage diagnostics; not a production normalizer."""

import csv
import hashlib
import io
import math
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from google.transit import gtfs_realtime_pb2 as pb

MAX_MEMBER_BYTES = 128 * 1024 * 1024
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024


@dataclass
class Schedule:
    trips: dict[str, list[dict[str, str]]]
    routes: set[str]
    shapes: set[str]
    calendars: dict[str, dict[str, str]]
    exceptions: dict[tuple[str, str], str]
    frequency_trips: set[str]
    sha256: str

    @classmethod
    def read(cls, path: Path) -> "Schedule":
        if path.stat().st_size > MAX_ARCHIVE_BYTES:
            raise ValueError("Static archive exceeds probe limit")
        with path.open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        with ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ValueError("Duplicate archive member")

            def rows(name: str, *, optional: bool = False) -> list[dict[str, str]]:
                if optional and name not in names:
                    return []
                if archive.getinfo(name).file_size > MAX_MEMBER_BYTES:
                    raise ValueError("Static member exceeds probe limit")
                with archive.open(name) as raw:
                    return list(csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig")))

            trips: dict[str, list[dict[str, str]]] = {}
            for row in rows("trips.txt"):
                trips.setdefault(row["trip_id"], []).append(row)
            points = Counter(row["shape_id"] for row in rows("shapes.txt"))
            calendars = rows("calendar.txt", optional=True)
            exceptions = rows("calendar_dates.txt", optional=True)
            if len({r["service_id"] for r in calendars}) != len(calendars):
                raise ValueError("Duplicate calendar service")
            if len({(r["service_id"], r["date"]) for r in exceptions}) != len(exceptions):
                raise ValueError("Duplicate calendar exception")
            return cls(
                trips=trips,
                routes={r["route_id"] for r in rows("routes.txt")},
                shapes={s for s, count in points.items() if count >= 2},
                calendars={r["service_id"]: r for r in calendars},
                exceptions={(r["service_id"], r["date"]): r["exception_type"] for r in exceptions},
                frequency_trips={r["trip_id"] for r in rows("frequencies.txt", optional=True)},
                sha256=digest,
            )

    def inventory(self) -> dict[str, Any]:
        return {
            "sha256": self.sha256,
            "trip_rows": sum(map(len, self.trips.values())),
            "duplicate_trip_ids": sum(len(rows) > 1 for rows in self.trips.values()),
            "routes": len(self.routes),
            "shapes_with_at_least_two_points": len(self.shapes),
            "trips_without_shape": sum(
                row.get("shape_id") not in self.shapes
                for rows in self.trips.values()
                for row in rows
            ),
            "calendar_start": min((r["start_date"] for r in self.calendars.values()), default=None),
            "calendar_end": max((r["end_date"] for r in self.calendars.values()), default=None),
        }

    def linkage(self, trip: Any) -> str:
        if trip.schedule_relationship != pb.TripDescriptor.SCHEDULED:
            return "non_scheduled"
        # Exact IDs only: suffix/fuzzy matches can connect a different service instance.
        candidates = self.trips.get(trip.trip_id, [])
        if not trip.trip_id:
            return "missing_trip_id"
        if not candidates:
            return "trip_not_found"
        if len(candidates) != 1:
            return "ambiguous_trip_id"
        row = candidates[0]
        if row["route_id"] not in self.routes:
            return "static_route_missing"
        if trip.route_id and trip.route_id != row["route_id"]:
            return "route_mismatch"
        if trip.HasField("direction_id") and str(trip.direction_id) != row.get("direction_id"):
            return "direction_mismatch"
        if row.get("shape_id") not in self.shapes:
            return "shape_missing"
        if trip.trip_id in self.frequency_trips:
            return "frequency_instance_unverified"
        if not trip.start_date:
            return "service_date_missing"
        try:
            day = datetime.strptime(trip.start_date, "%Y%m%d").date()
            if day.strftime("%Y%m%d") != trip.start_date:
                return "service_date_invalid"
        except ValueError:
            return "service_date_invalid"
        service = row["service_id"]
        exception = self.exceptions.get((service, trip.start_date))
        if exception is not None:
            return {"1": "linked", "2": "service_inactive"}.get(exception, "calendar_invalid")
        calendar = self.calendars.get(service)
        if calendar is None:
            return "service_date_unverified"
        weekday = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")[
            day.weekday()
        ]
        active = (
            calendar["start_date"] <= trip.start_date <= calendar["end_date"]
            and calendar[weekday] == "1"
        )
        return "linked" if active else "service_inactive"


def decode(data: bytes) -> Any:
    feed = pb.FeedMessage()
    feed.ParseFromString(data)
    if not feed.IsInitialized() or feed.header.gtfs_realtime_version not in {"1.0", "2.0"}:
        raise ValueError("Invalid GTFS-Realtime header or required fields")
    return feed


def summarize(feed: Any, schedule: Schedule, received_at: float) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    joins: Counter[str] = Counter()
    ages: list[float] = []
    for entity in feed.entity:
        if entity.is_deleted:
            counts["deleted"] += 1
            continue
        for kind in ("vehicle", "trip_update", "alert"):
            if not entity.HasField(kind):
                continue
            counts[kind] += 1
            value = getattr(entity, kind)
            if kind == "alert":
                counts["alert_selectors"] += len(value.informed_entity)
                continue
            joins[schedule.linkage(value.trip)] += 1
            for field in ("trip_id", "route_id", "start_date", "start_time", "direction_id"):
                counts["trip_missing_" + field] += not value.trip.HasField(field)
            if not value.vehicle.id:
                counts["missing_vehicle_id"] += 1
            if value.HasField("timestamp"):
                age = received_at - value.timestamp
                ages.append(age)
                counts["future_observation"] += age < 0
                counts["observation_over_120s"] += age > 120
                counts["observation_over_300s"] += age > 300
            else:
                counts["missing_observed_at"] += 1
            if kind == "vehicle":
                if not value.HasField("position"):
                    counts["missing_position"] += 1
                else:
                    p = value.position
                    counts["invalid_position"] += not (
                        math.isfinite(p.latitude)
                        and math.isfinite(p.longitude)
                        and -90 <= p.latitude <= 90
                        and -180 <= p.longitude <= 180
                    )
    ages.sort()
    return {
        "entities": len(feed.entity),
        "header_timestamp": feed.header.timestamp if feed.header.HasField("timestamp") else None,
        "incrementality": int(feed.header.incrementality),
        "counts": dict(sorted(counts.items())),
        "trip_linkage": dict(sorted(joins.items())),
        "observation_age_seconds": {
            "min": round(ages[0], 3) if ages else None,
            "p50": round(ages[(len(ages) - 1) // 2], 3) if ages else None,
            "max": round(ages[-1], 3) if ages else None,
        },
    }


def positions(feed: Any) -> dict[str, tuple[Any, ...]]:
    """Only unambiguous vehicle IDs participate in consecutive-position comparisons."""
    result = {}
    duplicates = set()
    for entity in feed.entity:
        if entity.is_deleted or not entity.HasField("vehicle"):
            continue
        v = entity.vehicle
        if not v.vehicle.id or not v.HasField("position"):
            continue
        if v.vehicle.id in result:
            duplicates.add(v.vehicle.id)
        result[v.vehicle.id] = (
            v.position.latitude,
            v.position.longitude,
            v.timestamp if v.HasField("timestamp") else None,
        )
    return {key: value for key, value in result.items() if key not in duplicates}


def entity_fingerprint(feed: Any) -> str:
    """Diagnostic only: exclude header timestamps and entity ordering, retain all entity fields."""
    digest = hashlib.sha256()
    for wire in sorted(e.SerializeToString(deterministic=True) for e in feed.entity):
        digest.update(len(wire).to_bytes(8, "big"))
        digest.update(wire)
    return digest.hexdigest()

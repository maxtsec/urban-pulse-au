"""Build a deterministic Southbank snapshot from a retained fixture capture."""

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

from pydantic import ValidationError

from urbanpulse.contracts.events import VehiclePositionChanged
from urbanpulse.location.city import Freshness, PositionProjection, position_freshness
from urbanpulse.location.status import AdverseFact, Coverage, CoverageState, assess_area

AREA_ID = "au-vic-melbourne-clue-southbank"
POLICY_VERSION = "southbank-fixture-v1"
MAX_SECONDS = 360
MAX_VEHICLES = 100
REQUIRED = frozenset({"transport_service", "weather_warnings"})


def geometry_revision(geometry: dict[str, Any]) -> str:
    canonical = json.dumps(geometry, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class CapturedCity:
    capture_id: str
    boundary: dict[str, Any]
    scenario: dict[str, Any]


class CityCapture(Protocol):
    def read(self) -> CapturedCity: ...


class SpatialMembership(Protocol):
    def covers(self, geometry: dict[str, Any], points: list[tuple[float, float]]) -> list[bool]: ...


class CityService:
    def __init__(self, capture: CityCapture, spatial: SpatialMembership) -> None:
        self.capture = capture
        self.spatial = spatial

    def geometry(self) -> dict[str, Any]:
        captured = self.capture.read()
        feature = captured.boundary
        return {
            "area_id": AREA_ID,
            "revision": geometry_revision(feature["geometry"]),
            "canonicalization": "sorted-keys-json-v1",
            "feature": feature,
        }

    def snapshot(self, seconds: int, scenario: str = "journey") -> dict[str, Any]:
        if seconds < 0 or seconds > MAX_SECONDS or scenario not in {"journey", "empty", "outage"}:
            raise ValueError("invalid fixture scenario or clock")
        captured = self.capture.read()
        boundary = captured.boundary
        revision = geometry_revision(boundary["geometry"])
        started_at = datetime.fromisoformat(captured.scenario["started_at"])
        at = started_at + timedelta(seconds=seconds)
        projection = PositionProjection()
        rejected = 0
        for frame in captured.scenario["frames"] if scenario != "empty" else []:
            if frame["at_seconds"] > seconds:
                continue
            try:
                event = VehiclePositionChanged.model_validate(frame["event"])
            except ValidationError:
                rejected += 1
                continue
            if event.upmode != "fixture" or event.source != "urn:urbanpulse:fixture:transport":
                rejected += 1
                continue
            projection.consume(event)
        entries = sorted(projection.positions.values(), key=lambda item: item.event.subject)
        points = [
            (entry.event.data.state.position.longitude, entry.event.data.state.position.latitude)
            for entry in entries
        ]
        # Service impact belongs to a stop, independently of vehicle movement.
        stop = captured.scenario["service_stop"]
        membership = self.spatial.covers(
            boundary["geometry"], [*points, tuple(stop["coordinates"])]
        )
        if len(membership) != len(points) + 1:
            raise ValueError("spatial adapter returned an incomplete result")
        vehicles = []
        for entry, inside in zip(entries, membership[:-1], strict=True):
            if not inside:
                continue
            state = entry.event.data.state
            freshness = position_freshness(state.observed_at, at)
            vehicles.append(
                {
                    "id": state.vehicle_id,
                    "label": captured.scenario["labels"].get(state.vehicle_id, state.vehicle_id),
                    "route_id": state.route_id,
                    "longitude": state.position.longitude,
                    "latitude": state.position.latitude,
                    "observed_at": state.observed_at,
                    "freshness": freshness,
                    "visible_on_map": freshness != Freshness.EXPIRED,
                    "event_id": entry.event.id,
                    "revision": entry.event.data.revision,
                    "capture_ids": entry.event.data.provenance.capture_ids,
                }
            )
        facts: tuple[AdverseFact, ...] = ()
        if scenario != "empty" and membership[-1]:
            facts = (
                AdverseFact(
                    id="synthetic-stop-disruption",
                    input_id="transport_service",
                    reason="Synthetic service interruption at Southbank stop A",
                    effective_from=started_at + timedelta(seconds=60),
                    resolved_at=started_at + timedelta(seconds=180),
                ),
            )
        transport_coverage = CoverageState.ERROR if scenario == "outage" else CoverageState.CURRENT
        assessment = assess_area(
            facts=facts,
            coverage=(
                Coverage("transport_service", transport_coverage),
                Coverage("weather_warnings", CoverageState.UNKNOWN),
                Coverage("planning", CoverageState.UNKNOWN),
            ),
            required_inputs=REQUIRED,
            at=at,
        )
        evidence = f"/api/v1/fixture/captures/{captured.capture_id}"
        return {
            "mode": "fixture",
            "area": {"id": AREA_ID, "name": "Southbank", "boundary_revision": revision},
            "geometry_url": f"/api/v1/areas/{AREA_ID}/boundaries/{revision}",
            "policy_version": POLICY_VERSION,
            "projection_version": hashlib.sha256(
                f"city-projection-v1:{captured.capture_id}:{revision}:{POLICY_VERSION}".encode()
            ).hexdigest(),
            "scenario": scenario,
            "clock": {"at": at, "seconds": seconds, "end_seconds": MAX_SECONDS},
            "assessment": asdict(assessment),
            "planning": {
                "state": "unknown",
                "as_of": None,
                "description": "Planning data not connected",
            },
            "vehicles": vehicles[:MAX_VEHICLES],
            "positions_total": len(vehicles),
            "positions_limit": MAX_VEHICLES,
            "positions_truncated": len(vehicles) > MAX_VEHICLES,
            "projection": {**projection.outcomes, "rejected": rejected},
            "evidence_url": evidence,
            "attribution": boundary["properties"],
        }

"""Build a deterministic Southbank snapshot from a retained fixture capture."""

import hashlib
import json
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from functools import cached_property
from typing import Any, Protocol

from pydantic import ValidationError

from urbanpulse.application.city_replay import ServiceFrame, received, service_at
from urbanpulse.application.planning import replay_planning
from urbanpulse.application.planning_replay import PlanningNormalizer, planning_steps
from urbanpulse.application.scenarios import scenario_policy
from urbanpulse.application.weather import replay_weather
from urbanpulse.application.weather_replay import WeatherNormalizer, weather_evidence
from urbanpulse.contracts.events import VehiclePositionChanged
from urbanpulse.location.city import Freshness, PositionProjection, position_freshness
from urbanpulse.location.status import AdverseFact, Coverage, CoverageState, assess_area
from urbanpulse.location.weather import WarningMembership

AREA_ID = "au-vic-melbourne-clue-southbank"
POLICY_VERSION = "southbank-fixture-v1"
MAX_SECONDS = 360
MAX_VEHICLES = 100
REQUIRED = frozenset({"transport_service", "weather_warnings"})


def geometry_revision(geometry: dict[str, Any]) -> str:
    canonical = json.dumps(geometry, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


class CaptureNotFoundError(Exception):
    """The requested capture identity is not available in this fixture service."""


@dataclass(frozen=True)
class CapturedCity:
    capture_id: str
    boundary: dict[str, Any]
    scenario: dict[str, Any]
    weather: dict[str, Any] | None = None
    planning: dict[str, Any] | None = None


class CityCapture(Protocol):
    def read(self) -> CapturedCity: ...


class SpatialMembership(WarningMembership, Protocol):
    def covers(self, geometry: dict[str, Any], points: list[tuple[float, float]]) -> list[bool]: ...


class CityService:
    def __init__(
        self,
        capture: CityCapture,
        spatial: SpatialMembership,
        weather_normalizer: WeatherNormalizer | None = None,
        planning_normalizer: PlanningNormalizer | None = None,
    ) -> None:
        self.capture = capture
        self.spatial = spatial
        self.weather_normalizer = weather_normalizer
        self.planning_normalizer = planning_normalizer

    @cached_property
    def captured(self) -> CapturedCity:
        # Pin verified fixture bytes for this service lifetime; restart to adopt a new bundle.
        return self.capture.read()

    @cached_property
    def boundary_revision(self) -> str:
        return geometry_revision(self.captured.boundary["geometry"])

    @cached_property
    def service_frames(self) -> tuple[ServiceFrame, ...]:
        frames = tuple(
            sorted(
                (
                    ServiceFrame.model_validate(raw)
                    for raw in self.captured.scenario["service_frames"]
                ),
                key=lambda frame: frame.at_seconds,
            )
        )
        if len({frame.at_seconds for frame in frames}) != len(frames):
            raise ValueError("service frames require distinct observation times")
        if any(frame.stop_id != self.captured.scenario["service_stop"]["id"] for frame in frames):
            raise ValueError("service frame references an unknown stop")
        return frames

    def geometry(self) -> dict[str, Any]:
        captured = self.captured
        feature = captured.boundary
        return {
            "area_id": AREA_ID,
            "revision": self.boundary_revision,
            "canonicalization": "sorted-keys-json-v1",
            "feature": deepcopy(feature),
        }

    def snapshot(self, seconds: int, scenario: str = "journey") -> dict[str, Any]:
        policy = scenario_policy(scenario)
        if seconds < 0 or seconds > MAX_SECONDS:
            raise ValueError("invalid fixture scenario or clock")
        captured = self.captured
        boundary = captured.boundary
        revision = self.boundary_revision
        started_at = datetime.fromisoformat(captured.scenario["started_at"])
        at = started_at + timedelta(seconds=seconds)
        outage_at = captured.scenario["outage_at_seconds"]
        projection = PositionProjection()
        rejected = 0
        for frame in captured.scenario["frames"]:
            if not received(frame["at_seconds"], seconds, policy, outage_at):
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
        fact, service_evidence = service_at(
            self.service_frames, started_at, seconds, policy, outage_at
        )
        facts: tuple[AdverseFact, ...] = (fact,) if fact is not None and membership[-1] else ()
        transport_coverage = (
            CoverageState.ERROR
            if policy.transport_outage and seconds >= outage_at
            else CoverageState.CURRENT
            if service_evidence is not None or policy.transport_empty
            else CoverageState.UNKNOWN
        )
        weather = None
        weather_coverage = CoverageState.UNKNOWN
        if policy.weather:
            if captured.weather is None or self.weather_normalizer is None:
                raise ValueError("weather fixture adapter is not configured")
            weather, weather_facts, weather_coverage = replay_weather(
                captured.weather,
                seconds,
                at,
                policy.weather_outage,
                boundary["geometry"],
                self.spatial,
                self.weather_normalizer,
            )
            facts += weather_facts
        planning: dict[str, Any] = {
            "state": "unknown",
            "as_of": None,
            "description": "Planning data not connected",
        }
        if policy.planning:
            if captured.planning is None or self.planning_normalizer is None:
                raise ValueError("planning fixture adapter is not configured")
            planning = replay_planning(
                captured.planning,
                seconds,
                at,
                policy.planning_outage,
                boundary["geometry"],
                self.spatial,
                self.planning_normalizer,
            )
        assessment = assess_area(
            facts=facts,
            coverage=(
                Coverage("transport_service", transport_coverage),
                Coverage("weather_warnings", weather_coverage),
                Coverage("planning", CoverageState(planning["state"])),
            ),
            required_inputs=REQUIRED,
            at=at,
        )
        evidence = (
            f"/api/v1/fixture/captures/{captured.capture_id}?seconds={seconds}&scenario={scenario}"
        )
        return {
            "mode": "fixture",
            "area": {"id": AREA_ID, "name": "Southbank", "boundary_revision": revision},
            "geometry_url": f"/api/v1/areas/{AREA_ID}/boundaries/{revision}",
            "policy_version": POLICY_VERSION,
            "projection_version": hashlib.sha256(
                f"city-projection-v7:{captured.capture_id}:{revision}:{POLICY_VERSION}".encode()
            ).hexdigest(),
            "scenario": scenario,
            "clock": {"at": at, "seconds": seconds, "end_seconds": MAX_SECONDS},
            "assessment": asdict(assessment),
            "service_evidence": service_evidence,
            "weather": weather,
            "planning": planning,
            "vehicles": vehicles[:MAX_VEHICLES],
            "positions_total": len(vehicles),
            "positions_limit": MAX_VEHICLES,
            "positions_truncated": len(vehicles) > MAX_VEHICLES,
            "projection": {**projection.outcomes, "rejected": rejected},
            "evidence_url": evidence,
            "attribution": deepcopy(boundary["properties"]),
        }

    def evidence(self, capture_id: str, seconds: int, scenario: str) -> dict[str, Any]:
        captured = self.captured
        if capture_id != captured.capture_id:
            raise CaptureNotFoundError("Unknown fixture capture")
        policy = scenario_policy(scenario)
        if seconds < 0 or seconds > MAX_SECONDS:
            raise ValueError("invalid fixture scenario or clock")
        outage_at = captured.scenario["outage_at_seconds"]
        events = [
            {
                "id": frame["event"]["id"],
                "kind": "position-attempt",
                "at_seconds": frame["at_seconds"],
                "capture_ids": frame["event"]["data"]["provenance"]["capture_ids"],
            }
            for frame in captured.scenario["frames"]
            if received(frame["at_seconds"], seconds, policy, outage_at)
        ]
        events.extend(
            {**frame.model_dump(mode="json"), "kind": "service-status"}
            for frame in self.service_frames
            if received(frame.at_seconds, seconds, policy, outage_at)
        )
        if policy.weather:
            if captured.weather is None or self.weather_normalizer is None:
                raise ValueError("weather fixture adapter is not configured")
            at = datetime.fromisoformat(captured.scenario["started_at"]) + timedelta(
                seconds=seconds
            )
            events.extend(
                weather_evidence(
                    captured.weather,
                    seconds,
                    at,
                    policy.weather_outage,
                    self.weather_normalizer,
                )
            )
        if policy.planning:
            if captured.planning is None or self.planning_normalizer is None:
                raise ValueError("planning fixture adapter is not configured")
            at = datetime.fromisoformat(captured.scenario["started_at"]) + timedelta(
                seconds=seconds
            )
            events.extend(
                step.evidence
                for step in planning_steps(
                    captured.planning,
                    seconds,
                    at,
                    policy.planning_outage,
                    self.planning_normalizer,
                )
            )
        return {
            "mode": "fixture",
            "capture_id": capture_id,
            "description": "Received fixture records at this clock; attempts may be rejected",
            "scenario_start": captured.scenario["started_at"],
            "seconds": seconds,
            "scenario": scenario,
            "synthetic_capture_references": True,
            "events": sorted(events, key=lambda event: (event["at_seconds"], event["id"])),
            "boundary_attribution": deepcopy(captured.boundary["properties"]),
        }

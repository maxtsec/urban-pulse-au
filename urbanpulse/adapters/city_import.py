"""Explicit fixture normalization/import; the serving API never calls this module."""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from urbanpulse.adapters.city_store import CityInputStore, engine_for
from urbanpulse.application.city import MAX_SECONDS, CapturedCity, CityService, SpatialMembership
from urbanpulse.application.planning_replay import planning_steps
from urbanpulse.application.service_events import service_events
from urbanpulse.application.weather_replay import weather_steps
from urbanpulse.contracts.events import VehiclePositionChanged


def prepare_import(
    captured: CapturedCity, spatial: SpatialMembership
) -> dict[str, list[dict[str, Any]]]:
    # Adapters are used only at explicit import, never on the serving/recovery path.
    from urbanpulse.adapters.planning_fixture import FixturePlanningNormalizer
    from urbanpulse.adapters.weather_fixture import FixtureWeatherNormalizer

    started = datetime.fromisoformat(captured.scenario["started_at"])
    at = started + timedelta(seconds=MAX_SECONDS)
    transport: list[dict[str, Any]] = []
    for frame in captured.scenario["frames"]:
        try:
            event = VehiclePositionChanged.model_validate(frame["event"])
            receipt_at = started + timedelta(seconds=frame["at_seconds"])
            if event.source != "urn:urbanpulse:fixture:transport" or event.time > receipt_at:
                raise ValueError("fixture event cannot reveal future or live data")
        except ValueError:
            event = None
        transport.append(
            {
                "kind": "position",
                "frame": {"at_seconds": frame["at_seconds"]},
                "event": event,
                "rejected_header": {
                    "id": frame["event"]["id"],
                    "data": {
                        "provenance": {
                            "capture_ids": frame["event"]["data"]["provenance"]["capture_ids"]
                        }
                    },
                }
                if event is None
                else None,
            }
        )

    class Capture:
        def read(self) -> CapturedCity:
            return captured

    frames = CityService(Capture(), spatial).service_frames
    for frame, service_event in zip(
        frames, service_events(frames, started, captured.scenario["service_stop"]), strict=True
    ):
        transport.append(
            {"kind": "service", "frame": frame.model_dump(mode="json"), "event": service_event}
        )
    weather = []
    if captured.weather:
        for step in weather_steps(
            captured.weather, MAX_SECONDS, at, False, FixtureWeatherNormalizer()
        ):
            weather.append(
                {
                    "frame": {
                        key: value
                        for key, value in step.frame.items()
                        if key not in {"state", "payload_id"}
                        or key == "state"
                        and step.frame["kind"] == "coverage"
                    },
                    "evidence": step.evidence,
                    "events": step.events,
                    "warning_records": step.warning_records,
                }
            )
    planning = []
    if captured.planning:
        for planning_step in planning_steps(
            captured.planning, MAX_SECONDS, at, False, FixturePlanningNormalizer()
        ):
            planning.append(
                {
                    "frame": {
                        key: value
                        for key, value in planning_step.frame.items()
                        if key != "payload_id"
                    },
                    "evidence": planning_step.evidence,
                    "event": planning_step.event,
                    "recapture": planning_step.recapture,
                }
            )
    return {"transport": transport, "weather": weather, "planning": planning}


def import_fixture(database_url: str, destination: Path) -> str:
    from urbanpulse.adapters.city_fixture import LocalCityCapture, capture_city
    from urbanpulse.adapters.postgis import PostgisMembership

    capture_id = capture_city(destination)
    captured = LocalCityCapture(destination, capture_id).read()
    engine = engine_for(database_url)
    try:
        scope = CityInputStore(engine).save(
            captured,
            prepare_import(captured, PostgisMembership(database_url)),
            activate="city-fixture",
        )
    finally:
        engine.dispose()
    return scope

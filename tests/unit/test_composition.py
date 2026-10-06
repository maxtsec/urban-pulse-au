"""Independent clocks, semantic transitions and source-only restart inputs."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from apps.api.main import app
from urbanpulse.adapters.city_fixture import LocalCityCapture, capture_city
from urbanpulse.adapters.city_import import prepare_import
from urbanpulse.application.city import AREA_ID, CityService
from urbanpulse.application.composition import ComposedCityService
from urbanpulse.application.delivery import CompositionUnavailable
from urbanpulse.application.inputs import CityInputs
from urbanpulse.application.planning_replay import PlanningStep
from urbanpulse.application.weather_replay import WeatherStep
from urbanpulse.contracts.composition import AreaStatusChanged, SourceCoverageChanged


class Spatial:
    def covers(self, area, points):
        return [True] * len(points)

    def overlaps(self, area, warning):
        return True


@pytest.fixture
def inputs(tmp_path):
    captured = LocalCityCapture(tmp_path, capture_city(tmp_path)).read()
    rows = prepare_import(captured, Spatial())
    return CityInputs(
        captured,
        tuple(WeatherStep(**row) for row in rows["weather"]),
        tuple(PlanningStep(**row) for row in rows["planning"]),
        tuple(row["event"] for row in rows["transport"] if row["kind"] == "service"),
    )


def service(inputs):
    return ComposedCityService(CityService(inputs, Spatial(), inputs=inputs), inputs)


def test_expiry_without_new_warning_emits_one_deterministic_transition(inputs):
    city = service(inputs)
    before = city.snapshot(239, "weather-outage")
    expired = city.snapshot(240, "weather-outage")
    later = city.snapshot(241, "weather-outage")
    assert before["assessment"]["condition"] == "degraded"
    assert expired["assessment"]["condition"] == "unknown"
    assert (
        len(expired["composition"]["area_events"]) == len(before["composition"]["area_events"]) + 1
    )
    assert later["composition"]["area_events"] == expired["composition"]["area_events"]
    event = AreaStatusChanged.model_validate(expired["composition"]["area_events"][-1])
    assert event.time == expired["clock"]["at"]
    assert event.data.provenance.capture_ids
    assert service(inputs).snapshot(240, "weather-outage") == expired


def test_concurrent_contexts_and_rewind_do_not_leak(inputs):
    city = service(inputs)
    requests = [
        (0, "city"),
        (360, "city"),
        (60, "city"),
        (200, "outage"),
        (240, "weather-outage"),
        (150, "planning-outage"),
        (0, "city"),
    ]
    isolated = [service(inputs).snapshot(*request) for request in requests]
    with ThreadPoolExecutor(max_workers=4) as pool:
        actual = list(pool.map(lambda request: city.snapshot(*request), requests))
    assert actual == isolated
    assert actual[0] == actual[-1]
    assert actual[0]["assessment"]["reasons"] == ()
    assert all(
        event["data"]["state"]["evaluated_at"]
        <= actual[2]["clock"]["at"].isoformat().replace("+00:00", "Z")
        for event in actual[2]["composition"]["area_events"]
    )


def test_planning_profile_changes_do_not_generate_area_condition_events(inputs):
    # The authored weather recovery is also at 270; hold it constant to isolate planning.
    inputs = replace(
        inputs, weather=tuple(step for step in inputs.weather if step.frame["at_seconds"] < 270)
    )
    city = service(inputs)
    first = city.snapshot(269, "city")
    recovered = city.snapshot(270, "city")
    assert first["planning"]["state"] != recovered["planning"]["state"]
    assert first["composition"]["area_events"] == recovered["composition"]["area_events"]
    for event in recovered["composition"]["area_events"]:
        assert {item["input_id"] for item in event["data"]["state"]["coverage"]} == {
            "transport_service",
            "weather_warnings",
        }


def test_envelope_rejects_identity_future_receipt_and_impossible_condition(inputs):
    view = service(inputs).snapshot(60, "city")
    event = view["composition"]["area_events"][-1]
    bad = {**event, "subject": "unrelated-area"}
    with pytest.raises(ValidationError):
        AreaStatusChanged.model_validate(bad)
    model = AreaStatusChanged.model_validate(event).model_dump(mode="json")
    model["data"]["state"]["condition"] = "normal"
    with pytest.raises(ValidationError):
        AreaStatusChanged.model_validate(model)
    coverage = view["composition"]["coverage_events"][0]
    coverage["data"]["state"]["last_successful_received_at"] = "2099-01-01T00:00:00Z"
    with pytest.raises(ValidationError):
        SourceCoverageChanged.model_validate(coverage)


def test_failed_composition_returns_503_and_fresh_reconstruction_recovers(inputs, monkeypatch):
    class FailedPublisher:
        def publish(self, wire, handlers):
            raise CompositionUnavailable("handler retries exhausted")

    failed = ComposedCityService(
        CityService(
            inputs, Spatial(), inputs=inputs, publisher_factory=lambda _: FailedPublisher()
        ),
        inputs,
    )
    monkeypatch.setattr("apps.api.city.city_service", lambda request: failed)
    with TestClient(app) as client:
        assert client.get(f"/api/v1/areas/{AREA_ID}?scenario=city").status_code == 503
        monkeypatch.setattr("apps.api.city.city_service", lambda request: service(inputs))
        assert client.get(f"/api/v1/areas/{AREA_ID}?scenario=city").status_code == 200


def test_evidence_does_not_project_or_query_spatial_membership(inputs):
    class NoSpatial:
        def covers(self, *args):
            pytest.fail("evidence must not evaluate membership")

        def overlaps(self, *args):
            pytest.fail("evidence must not evaluate warnings")

    city = CityService(inputs, NoSpatial(), inputs=inputs)
    evidence = city.evidence(inputs.captured.capture_id, 120, "city")
    assert evidence["events"]
    assert all(event["at_seconds"] <= 120 for event in evidence["events"])


def test_coverage_refresh_keeps_original_observation_identity(inputs):
    city = service(inputs)
    before = city.snapshot(61, "city")
    after = city.snapshot(62, "city")
    assert before["composition"]["coverage_events"] == after["composition"]["coverage_events"]
    assert before["composition"]["area_events"] == after["composition"]["area_events"]


def test_missing_selected_import_is_503_without_implicit_setup(monkeypatch):
    class Store:
        def active_scope(self):
            raise ValueError("city inputs not selected")

        def load(self, scope):
            pytest.fail("missing selection must not load history")

    monkeypatch.setattr("apps.api.city.input_store", lambda request: Store())
    with TestClient(app) as client:
        response = client.get(f"/api/v1/areas/{AREA_ID}")
    assert response.status_code == 503
    assert "assessment" not in response.json()


def test_database_unavailability_is_503_without_empty_fixture_fallback(monkeypatch):
    from sqlalchemy.exc import OperationalError

    class Store:
        def active_scope(self):
            raise OperationalError("read", {}, Exception("database unavailable"))

    monkeypatch.setattr("apps.api.city.input_store", lambda request: Store())
    with TestClient(app) as client:
        response = client.get(f"/api/v1/areas/{AREA_ID}")
    assert response.status_code == 503
    assert "assessment" not in response.json()

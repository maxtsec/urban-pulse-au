import copy
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from urbanpulse.adapters.city_fixture import LocalCityCapture, capture_city
from urbanpulse.application.city import AREA_ID, CapturedCity, CityService, geometry_revision
from urbanpulse.contracts.events import VehiclePositionChanged
from urbanpulse.location.city import Freshness, PositionProjection, position_freshness


class MemoryCapture:
    def __init__(self, captured):
        self.captured = captured

    def read(self):
        return self.captured


class FixedMembership:
    def covers(self, geometry, points):
        return [True] * len(points)


@pytest.fixture
def captured(tmp_path):
    digest = capture_city(tmp_path)
    return LocalCityCapture(tmp_path, digest).read()


@pytest.mark.parametrize(
    ("seconds", "expected"), [(119, "current"), (120, "stale"), (299, "stale"), (300, "expired")]
)
def test_freshness_boundaries_use_observation_age(seconds, expected):
    observed = datetime(2026, 10, 4, tzinfo=UTC)
    assert position_freshness(observed, observed + timedelta(seconds=seconds)) == expected


def test_missing_and_future_source_times_are_never_current():
    at = datetime(2026, 10, 4, tzinfo=UTC)
    assert position_freshness(None, at) == Freshness.UNKNOWN
    assert position_freshness(at + timedelta(seconds=1), at) == Freshness.UNKNOWN


def test_capture_is_retrievable_idempotent_and_integrity_checked(tmp_path):
    digest = capture_city(tmp_path)
    assert capture_city(tmp_path) == digest
    store = LocalCityCapture(tmp_path, digest)
    assert store.read().capture_id == digest
    store.path.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="integrity"):
        store.read()
    with pytest.raises(ValueError, match="identity"):
        capture_city(tmp_path)


def test_projection_replays_without_replacing_newer_positions(captured):
    projection = PositionProjection()
    frames = captured.scenario["frames"]
    for index in (0, 3, 4, 5, 7):
        projection.consume(VehiclePositionChanged.model_validate(frames[index]["event"]))
    current = projection.positions["yarra-trams/synthetic-tram-01"]
    assert current.event.data.revision == 2
    assert current.event.data.state.position.longitude == 144.9622
    assert projection.outcomes == {"apply": 2, "duplicate": 1, "superseded": 1, "conflict": 1}


def test_snapshots_are_request_local_and_replay_is_deterministic(captured):
    service = CityService(MemoryCapture(captured), FixedMembership())
    initial = service.snapshot(0)
    assert service.snapshot(150)["assessment"]["condition"] == "degraded"
    assert service.snapshot(180)["assessment"]["condition"] == "unknown"
    assert service.snapshot(0) == initial
    assert service.snapshot(150) == service.snapshot(150)
    assert initial["assessment"]["incomplete_inputs"] == ("weather_warnings",)
    assert initial["planning"]["as_of"] is None


def test_outage_does_not_resolve_known_fact_and_empty_is_not_healthy(captured):
    service = CityService(MemoryCapture(captured), FixedMembership())
    outage = service.snapshot(120, "outage")
    assert outage["assessment"]["condition"] == "degraded"
    assert "transport_service" in outage["assessment"]["incomplete_inputs"]
    empty = service.snapshot(120, "empty")
    assert empty["vehicles"] == []
    assert empty["assessment"]["condition"] == "unknown"


def test_invalid_positions_are_withheld_with_quality_evidence(captured):
    result = CityService(MemoryCapture(captured), FixedMembership()).snapshot(90)
    assert result["projection"]["rejected"] == 1
    assert all(-90 <= vehicle["latitude"] <= 90 for vehicle in result["vehicles"])


def test_geometry_revision_ignores_metadata_and_detects_coordinate_changes(captured):
    boundary = copy.deepcopy(captured.boundary)
    original = geometry_revision(boundary["geometry"])
    boundary["properties"]["retrieved_date"] = "later"
    assert geometry_revision(boundary["geometry"]) == original
    boundary["geometry"]["coordinates"][0][0][0][0] += 0.00001
    assert geometry_revision(boundary["geometry"]) != original


@pytest.fixture
def client(monkeypatch, captured):
    service = CityService(MemoryCapture(captured), FixedMembership())
    monkeypatch.setattr("apps.api.city.city_service", lambda: service)
    with TestClient(app) as client:
        yield client


def test_area_api_boundary_and_evidence_contract(client):
    response = client.get(f"/api/v1/areas/{AREA_ID}?seconds=30")
    assert response.status_code == 200
    snapshot = response.json()
    assert snapshot["mode"] == "fixture"
    assert snapshot["positions_truncated"] is False
    boundary = client.get(snapshot["geometry_url"])
    assert boundary.status_code == 200
    assert boundary.json()["feature"]["properties"]["licence"] == "CC BY 4.0"
    assert client.get(snapshot["evidence_url"]).json()["mode"] == "fixture"
    assert client.get(f"/api/v1/areas/{AREA_ID}/boundaries/unknown").status_code == 404
    assert client.get("/api/v1/fixture/captures/unknown").status_code == 404


@pytest.mark.parametrize("query", ["seconds=-1", "seconds=361", "seconds=1.5", "scenario=live"])
def test_invalid_clock_and_scenario_are_rejected(client, query):
    assert client.get(f"/api/v1/areas/{AREA_ID}?{query}").status_code == 422


def test_unknown_area_is_404(client):
    assert client.get("/api/v1/areas/not-a-pilot").status_code == 404


def test_unavailable_spatial_service_is_503_without_leaking_details(monkeypatch, captured):
    class FailedMembership:
        def covers(self, geometry, points):
            raise OSError("private connection details")

    service = CityService(MemoryCapture(captured), FailedMembership())
    monkeypatch.setattr("apps.api.city.city_service", lambda: service)
    with TestClient(app) as client:
        response = client.get(f"/api/v1/areas/{AREA_ID}")
    assert response.status_code == 503
    assert "private" not in response.text


def test_position_limit_is_explicit(captured):
    scenario = copy.deepcopy(captured.scenario)
    original = scenario["frames"][0]
    scenario["frames"] = []
    for i in range(101):
        frame = copy.deepcopy(original)
        event = frame["event"]
        event["id"] = f"event-{i}"
        event["subject"] = event["data"]["state"]["vehicle_id"] = f"tram-{i}"
        scenario["frames"].append(frame)
    result = CityService(
        MemoryCapture(CapturedCity(captured.capture_id, captured.boundary, scenario)),
        FixedMembership(),
    ).snapshot(0)
    assert len(result["vehicles"]) == 100
    assert result["positions_total"] == 101
    assert result["positions_truncated"] is True


@pytest.mark.parametrize("field,value", [("upmode", "live"), ("source", "urn:other:transport")])
def test_fixture_boundary_withholds_live_or_foreign_events(captured, field, value):
    scenario = copy.deepcopy(captured.scenario)
    scenario["frames"][0]["event"][field] = value
    result = CityService(
        MemoryCapture(CapturedCity(captured.capture_id, captured.boundary, scenario)),
        FixedMembership(),
    ).snapshot(0)
    assert result["projection"]["rejected"] == 1
    assert len(result["vehicles"]) == 2

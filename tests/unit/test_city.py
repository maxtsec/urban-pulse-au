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
    monkeypatch.setattr("apps.api.city.city_service", lambda request: service)
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
    monkeypatch.setattr("apps.api.city.city_service", lambda request: service)
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


@pytest.mark.parametrize("seconds", [60, 120, 179])
def test_disruption_never_exposes_resolution_before_its_frame(captured, seconds):
    service = CityService(MemoryCapture(captured), FixedMembership())
    snapshot = service.snapshot(seconds)
    reason = snapshot["assessment"]["reasons"][0]
    assert reason["resolved_at"] is None
    assert reason["effective_until"] is None
    assert snapshot["service_evidence"]["event_id"] == "city-service-60"
    evidence = service.evidence(captured.capture_id, seconds, "journey")
    assert all(event["at_seconds"] <= seconds for event in evidence["events"])
    assert "city-service-180" not in {event["id"] for event in evidence["events"]}


@pytest.mark.parametrize("seconds", [180, 200, 360])
def test_outage_preserves_known_disruption_without_receiving_resolution(captured, seconds):
    service = CityService(MemoryCapture(captured), FixedMembership())
    snapshot = service.snapshot(seconds, "outage")
    assert snapshot["assessment"]["condition"] == "degraded"
    assert snapshot["assessment"]["reasons"][0]["resolved_at"] is None
    assert snapshot["service_evidence"]["event_id"] == "city-service-60"
    assert snapshot["assessment"]["incomplete_inputs"] == ("transport_service", "weather_warnings")
    evidence = service.evidence(captured.capture_id, seconds, "outage")
    assert all(event["at_seconds"] < 90 for event in evidence["events"])
    assert snapshot["projection"]["rejected"] == 0  # invalid 90s frame was never received


@pytest.mark.parametrize(
    "outage_at,condition",
    [(0, "unknown"), (60, "unknown"), (90, "degraded"), (180, "degraded"), (181, "unknown")],
)
def test_outage_cutoff_gates_all_service_knowledge(captured, outage_at, condition):
    scenario = copy.deepcopy(captured.scenario)
    scenario["outage_at_seconds"] = outage_at
    service = CityService(
        MemoryCapture(CapturedCity(captured.capture_id, captured.boundary, scenario)),
        FixedMembership(),
    )
    snapshot = service.snapshot(200, "outage")
    assert snapshot["assessment"]["condition"] == condition
    if outage_at == 0:
        assert snapshot["vehicles"] == []
        assert snapshot["service_evidence"] is None
        assert service.evidence(captured.capture_id, 200, "outage")["events"] == []


def test_outage_starts_after_known_service_frame_and_rewind_is_isolated(captured):
    service = CityService(MemoryCapture(captured), FixedMembership())
    before = service.snapshot(89, "outage")
    assert before["assessment"]["incomplete_inputs"] == ("weather_warnings",)
    assert "transport_service" in service.snapshot(90, "outage")["assessment"]["incomplete_inputs"]
    assert service.snapshot(200)["assessment"]["reasons"] == ()
    assert service.snapshot(200, "outage")["assessment"]["reasons"]
    assert service.snapshot(89, "outage") == before


def test_service_behavior_comes_from_retained_frames(captured):
    scenario = copy.deepcopy(captured.scenario)
    scenario["service_frames"][1]["reason"] = "Different captured interruption"
    scenario["service_frames"][2]["at_seconds"] = 240
    service = CityService(
        MemoryCapture(CapturedCity(captured.capture_id, captured.boundary, scenario)),
        FixedMembership(),
    )
    assert (
        service.snapshot(200)["assessment"]["reasons"][0]["reason"]
        == "Different captured interruption"
    )
    assert service.snapshot(240)["assessment"]["reasons"] == ()


def test_evidence_route_uses_snapshot_clock_and_service_provenance(client):
    snapshot = client.get(f"/api/v1/areas/{AREA_ID}?seconds=60").json()
    evidence = client.get(snapshot["evidence_url"]).json()
    records = {event["id"]: event for event in evidence["events"]}
    service = snapshot["service_evidence"]
    assert records[service["event_id"]]["capture_ids"] == service["capture_ids"]
    assert records[service["event_id"]]["kind"] == "service-status"
    assert "city-service-180" not in records
    for query in ("seconds=-1", "seconds=361", "scenario=live"):
        path = snapshot["evidence_url"].split("?")[0]
        assert client.get(f"{path}?{query}").status_code == 422


def test_service_pins_verified_bundle_and_geometry_without_repeated_reads(captured):
    class CountingCapture:
        calls = 0

        def read(self):
            self.calls += 1
            return captured

    capture = CountingCapture()
    service = CityService(capture, FixedMembership())
    initial = service.snapshot(60)
    geometry = service.geometry()
    geometry["feature"]["geometry"]["coordinates"].clear()
    service.evidence(captured.capture_id, 60, "journey")
    assert service.snapshot(60) == initial
    assert capture.calls == 1


def test_disrupted_update_preserves_episode_identity_and_start_but_updates_evidence(captured):
    scenario = copy.deepcopy(captured.scenario)
    update = {
        **scenario["service_frames"][1],
        "id": "service-update-120",
        "at_seconds": 120,
        "reason": "Updated interruption detail",
        "capture_ids": ["capture-update-120"],
    }
    scenario["service_frames"].append(update)
    service = CityService(
        MemoryCapture(CapturedCity(captured.capture_id, captured.boundary, scenario)),
        FixedMembership(),
    )
    first = service.snapshot(60)["assessment"]["reasons"][0]
    updated = service.snapshot(150)
    fact = updated["assessment"]["reasons"][0]
    assert fact["id"] == first["id"]
    assert fact["effective_from"] == first["effective_from"]
    assert fact["reason"] == "Updated interruption detail"
    assert updated["service_evidence"]["event_id"] == "service-update-120"
    assert updated["service_evidence"]["capture_ids"] == ("capture-update-120",)
    assert service.snapshot(150, "outage")["assessment"]["reasons"][0] == first
    assert service.snapshot(180)["assessment"]["reasons"] == ()
    assert service.snapshot(60)["assessment"]["reasons"][0] == first


def test_disruption_after_received_clear_starts_a_new_episode(captured):
    scenario = copy.deepcopy(captured.scenario)
    scenario["service_frames"].append(
        {
            **scenario["service_frames"][1],
            "id": "new-episode-240",
            "at_seconds": 240,
            "capture_ids": ["capture-new-240"],
        }
    )
    service = CityService(
        MemoryCapture(CapturedCity(captured.capture_id, captured.boundary, scenario)),
        FixedMembership(),
    )
    assert service.snapshot(200)["assessment"]["reasons"] == ()
    fact = service.snapshot(240)["assessment"]["reasons"][0]
    assert fact["id"] == "new-episode-240"
    assert fact["effective_from"] == datetime(2026, 10, 4, 0, 4, tzinfo=UTC)


@pytest.mark.parametrize("transport_mode", ["empty", "outage"])
def test_transport_behavior_follows_registry_in_snapshot_and_evidence(
    captured, monkeypatch, transport_mode
):
    from dataclasses import replace

    from urbanpulse.application.scenarios import SCENARIOS, Scenario

    captured.scenario["outage_at_seconds"] = 120
    city = CityService(MemoryCapture(captured), FixedMembership())
    expected = city.snapshot(270, transport_mode)
    expected_evidence = city.evidence(captured.capture_id, 270, transport_mode)["events"]
    # A different scenario name must inherit all transport behavior from its policy.
    monkeypatch.setitem(
        SCENARIOS,
        Scenario.JOURNEY,
        replace(
            SCENARIOS[Scenario.JOURNEY],
            transport_empty=transport_mode == "empty",
            transport_outage=transport_mode == "outage",
        ),
    )
    actual = city.snapshot(270, "journey")
    for field in ("vehicles", "assessment", "service_evidence", "projection"):
        assert actual[field] == expected[field]
    evidence = city.evidence(captured.capture_id, 270, "journey")["events"]
    assert evidence == expected_evidence
    if transport_mode == "empty":
        assert actual["vehicles"] == [] and evidence == []
    else:
        assert any(
            reason["input_id"] == "transport_service" for reason in actual["assessment"]["reasons"]
        )
        assert all(frame["at_seconds"] < 120 for frame in evidence)

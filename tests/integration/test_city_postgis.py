"""Run with pytest -m integration against local PostGIS; never substitute a mock."""

import copy
import os

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from urbanpulse.adapters.city_fixture import LocalCityCapture, capture_city
from urbanpulse.adapters.postgis import PostgisMembership
from urbanpulse.application.city import AREA_ID, CapturedCity, CityService, geometry_revision

pytestmark = pytest.mark.integration


@pytest.fixture
def spatial():
    return PostgisMembership(
        os.environ.get(
            "URBANPULSE_TEST_DATABASE_URL",
            "postgresql://urbanpulse:urbanpulse_local@127.0.0.1:5432/urbanpulse",
        )
    )


@pytest.fixture
def capture(tmp_path):
    return LocalCityCapture(tmp_path, capture_city(tmp_path))


def test_real_boundary_inside_edge_and_outside(spatial, capture):
    geometry = capture.read().boundary["geometry"]
    vertex = geometry["coordinates"][0][0][0]
    assert spatial.covers(geometry, [(144.9617, -37.82529), tuple(vertex), (144.98, -37.81)]) == [
        True,
        True,
        False,
    ]


@pytest.mark.parametrize(
    "geometry",
    [
        {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [0, 1], [1, 0], [0, 0]]]},
        {"type": "Polygon", "coordinates": []},
        {"type": "Point", "coordinates": [144.96, -37.82]},
        {"type": "Polygon", "coordinates": [[[181, 0], [182, 0], [182, 1], [181, 0]]]},
    ],
)
def test_invalid_or_wrong_geometry_is_rejected(spatial, geometry):
    with pytest.raises(ValueError, match="invalid area boundary"):
        spatial.covers(geometry, [])


def test_capture_projection_api_uses_real_membership_and_clock(monkeypatch, capture, spatial):
    service = CityService(capture, spatial)
    monkeypatch.setattr("apps.api.city.city_service", lambda: service)
    with TestClient(app) as client:
        initial = client.get(f"/api/v1/areas/{AREA_ID}").json()
        moved = client.get(f"/api/v1/areas/{AREA_ID}?seconds=60").json()
        stale = client.get(f"/api/v1/areas/{AREA_ID}?seconds=150").json()
        expired = client.get(f"/api/v1/areas/{AREA_ID}?seconds=330").json()
    assert len(initial["vehicles"]) == 3
    assert len(moved["vehicles"]) == 2
    assert moved["assessment"]["condition"] == "degraded"
    assert moved["vehicles"][0]["revision"] == 2
    assert stale["vehicles"][0]["freshness"] == "stale"
    assert expired["vehicles"][0]["visible_on_map"] is False
    assert expired["vehicles"][0]["freshness"] == "expired"
    assert expired["assessment"]["condition"] == "unknown"
    assert expired["projection"] == {
        "apply": 5,
        "duplicate": 1,
        "superseded": 1,
        "conflict": 1,
        "rejected": 1,
    }


def test_changed_boundary_recomputes_membership(spatial, capture):
    captured = capture.read()
    old = CityService(capture, spatial).snapshot(0)
    changed = copy.deepcopy(captured.boundary)
    changed["geometry"] = {
        "type": "Polygon",
        "coordinates": [[[144.98, -37.81], [144.99, -37.81], [144.99, -37.80], [144.98, -37.81]]],
    }

    class ChangedCapture:
        def read(self):
            return CapturedCity(captured.capture_id, changed, captured.scenario)

    new = CityService(ChangedCapture(), spatial).snapshot(0)
    assert old["projection_version"] != new["projection_version"]
    assert old["vehicles"]
    assert new["vehicles"] == []
    assert old["area"]["boundary_revision"] != new["area"]["boundary_revision"]
    assert new["area"]["boundary_revision"] == geometry_revision(changed["geometry"])


def test_spatial_cache_reuses_identical_input_but_rechecks_new_geometry(
    monkeypatch, spatial, capture
):
    import psycopg

    connect = psycopg.connect
    calls = []

    def counted_connect(*args, **kwargs):
        calls.append(True)
        return connect(*args, **kwargs)

    monkeypatch.setattr("urbanpulse.adapters.postgis.psycopg.connect", counted_connect)
    geometry = capture.read().boundary["geometry"]
    point = (144.9617, -37.82529)
    assert spatial.covers(geometry, [point]) == [True]
    assert spatial.covers(copy.deepcopy(geometry), [point]) == [True]
    assert len(calls) == 1
    changed = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}
    assert spatial.covers(changed, [point]) == [False]
    assert len(calls) == 2


def test_real_api_outage_keeps_known_fact_past_unreceived_resolution(monkeypatch, capture, spatial):
    service = CityService(capture, spatial)
    monkeypatch.setattr("apps.api.city.city_service", lambda: service)
    with TestClient(app) as client:
        before = client.get(f"/api/v1/areas/{AREA_ID}?seconds=60").json()
        outage = client.get(f"/api/v1/areas/{AREA_ID}?seconds=200&scenario=outage").json()
        journey = client.get(f"/api/v1/areas/{AREA_ID}?seconds=200").json()
        evidence = client.get(outage["evidence_url"]).json()
    assert before["assessment"]["reasons"][0]["resolved_at"] is None
    assert outage["assessment"]["condition"] == "degraded"
    assert journey["assessment"]["condition"] == "unknown"
    assert all(event["id"] != "city-service-180" for event in evidence["events"])

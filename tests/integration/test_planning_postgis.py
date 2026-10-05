import os

import pytest

from urbanpulse.adapters.city_fixture import LocalCityCapture, capture_city
from urbanpulse.adapters.planning_fixture import FixturePlanningNormalizer
from urbanpulse.adapters.postgis import PostgisMembership
from urbanpulse.adapters.weather_fixture import FixtureWeatherNormalizer
from urbanpulse.application.city import CityService
from urbanpulse.location.planning import PlanningProjection

pytestmark = pytest.mark.integration


@pytest.fixture
def spatial():
    return PostgisMembership(
        os.environ.get(
            "URBANPULSE_TEST_DATABASE_URL",
            "postgresql://urbanpulse:urbanpulse_local@127.0.0.1:5432/urbanpulse",
        )
    )


def test_real_southbank_planning_membership_and_three_domain_snapshot(tmp_path, spatial):
    capture = LocalCityCapture(tmp_path, capture_city(tmp_path))
    city = CityService(capture, spatial, FixtureWeatherNormalizer(), FixturePlanningNormalizer())
    first = city.snapshot(0, "city")["planning"]
    assert len(first["records"]) == 3
    assert first["state"] == "current"
    assert all(r["development_key"] != "synthetic-outside" for r in first["records"])
    second = city.snapshot(150, "city")["planning"]
    assert len(second["records"]) == 2 and len(second["unlocated_records"]) == 1
    recovered = city.snapshot(270, "city")
    assert len(recovered["planning"]["records"]) == 3
    assert recovered["assessment"]["condition"] == "normal"
    assert city.snapshot(270, "planning-outage")["assessment"]["condition"] == "normal"


@pytest.mark.parametrize(
    "position,member",
    [((0, 1), True), ((0, 0), True), ((1, 1), True), ((-0.001, 1), False), ((3, 3), False)],
)
def test_planning_points_include_edge_vertex_and_no_buffer(tmp_path, spatial, position, member):
    data = LocalCityCapture(tmp_path, capture_city(tmp_path)).read().planning
    data["payloads"]["initial"]["records"] = data["payloads"]["initial"]["records"][:1]
    data["payloads"]["initial"]["records"][0]["position"] = {
        "longitude": position[0],
        "latitude": position[1],
    }
    event = FixturePlanningNormalizer().snapshot(data["payloads"]["initial"], data["frames"][0])
    projection = PlanningProjection()
    projection.consume(event)
    geometry = {"type": "Polygon", "coordinates": [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]]}
    profile = projection.profile(geometry, spatial)
    assert bool(profile["records"]) is member
    assert profile["unlocated_records"] == []

import copy
import os

import pytest

from urbanpulse.adapters.city_fixture import LocalCityCapture, capture_city
from urbanpulse.adapters.postgis import PostgisMembership
from urbanpulse.adapters.weather_fixture import FixtureWeatherNormalizer
from urbanpulse.application.city import CityService

pytestmark = pytest.mark.integration


def polygon(x0, y0, x1, y1):
    return {"type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}


@pytest.fixture
def spatial():
    return PostgisMembership(
        os.environ.get(
            "URBANPULSE_TEST_DATABASE_URL",
            "postgresql://urbanpulse:urbanpulse_local@127.0.0.1:5432/urbanpulse",
        )
    )


@pytest.mark.parametrize(
    "warning,expected",
    [
        (polygon(1, 1, 3, 3), True),
        (polygon(0.5, 0.5, 1, 1), True),
        (polygon(0, 0, 2, 2), True),
        (polygon(2, 0, 3, 2), False),
        (polygon(2, 2, 3, 3), False),
        (polygon(3, 3, 4, 4), False),
        ({"type": "Polygon", "coordinates": [[[0, 0], [2, 2], [0, 2], [2, 0], [0, 0]]]}, None),
    ],
)
def test_real_polygon_interior_overlap_not_just_boundary(spatial, warning, expected):
    assert spatial.overlaps(polygon(0, 0, 2, 2), warning) is expected


def test_holes_and_multipolygons(spatial):
    area = polygon(0, 0, 5, 5)
    area["coordinates"].extend(polygon(1, 1, 4, 4)["coordinates"])
    assert spatial.overlaps(area, polygon(2, 2, 3, 3)) is False
    multi = {
        "type": "MultiPolygon",
        "coordinates": [polygon(2, 2, 3, 3)["coordinates"], polygon(4.5, 4.5, 6, 6)["coordinates"]],
    }
    assert spatial.overlaps(area, multi) is True


def test_real_retained_weather_replay(spatial, tmp_path):
    capture = LocalCityCapture(tmp_path, capture_city(tmp_path))
    city = CityService(capture, spatial, FixtureWeatherNormalizer())
    at = city.snapshot(180, "weather")
    assert at["assessment"]["condition"] == "degraded"
    assert {r["input_id"] for r in at["assessment"]["reasons"]} == {"weather_warnings"}
    assert city.snapshot(240, "weather")["assessment"]["condition"] == "unknown"
    assert city.snapshot(270, "weather")["assessment"]["condition"] == "normal"
    assert city.snapshot(200, "weather-outage")["assessment"]["condition"] == "degraded"
    assert city.snapshot(240, "weather-outage")["assessment"]["condition"] == "unknown"


def test_polygon_cache_uses_geometry_and_not_clock(spatial, monkeypatch):
    import psycopg

    connect = psycopg.connect
    calls = []

    def counted(*args, **kwargs):
        calls.append(True)
        return connect(*args, **kwargs)

    monkeypatch.setattr("urbanpulse.adapters.postgis.psycopg.connect", counted)
    area, warning = polygon(0, 0, 2, 2), polygon(1, 1, 3, 3)
    assert spatial.overlaps(area, warning) is True
    assert spatial.overlaps(copy.deepcopy(area), copy.deepcopy(warning)) is True
    assert len(calls) == 1
    assert spatial.overlaps(polygon(4, 4, 5, 5), warning) is False
    assert len(calls) == 2

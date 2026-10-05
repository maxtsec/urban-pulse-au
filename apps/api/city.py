"""Read-only fixture city endpoints; every clock is explicit and request-local."""

from functools import lru_cache
from typing import Any

import psycopg
from fastapi import APIRouter, HTTPException, Query

from urbanpulse.adapters.city_fixture import LocalCityCapture, capture_city
from urbanpulse.adapters.planning_fixture import FixturePlanningNormalizer
from urbanpulse.adapters.postgis import PostgisMembership
from urbanpulse.adapters.weather_fixture import FixtureWeatherNormalizer
from urbanpulse.application.city import AREA_ID, MAX_SECONDS, CaptureNotFoundError, CityService
from urbanpulse.application.scenarios import Scenario
from urbanpulse.config import Settings

router = APIRouter()


@lru_cache(maxsize=1)
def city_service() -> CityService:
    settings = Settings()
    capture_id = capture_city(settings.city_capture_path)
    return CityService(
        LocalCityCapture(settings.city_capture_path, capture_id),
        PostgisMembership(settings.database_url),
        FixtureWeatherNormalizer(),
        FixturePlanningNormalizer(),
    )


def require_area(area_id: str) -> None:
    if area_id != AREA_ID:
        raise HTTPException(status_code=404, detail="Unknown area")


@router.get("/api/v1/areas/{area_id}")
def area_snapshot(
    area_id: str,
    seconds: int = Query(default=0, ge=0, le=MAX_SECONDS),
    scenario: Scenario = Scenario.JOURNEY,
) -> dict[str, Any]:
    require_area(area_id)
    try:
        return city_service().snapshot(seconds, scenario)
    except (psycopg.Error, OSError, ValueError, KeyError) as error:
        raise HTTPException(
            status_code=503, detail="City snapshot unavailable; check local services"
        ) from error


@router.get("/api/v1/areas/{area_id}/boundaries/{revision}")
def area_boundary(area_id: str, revision: str) -> dict[str, Any]:
    require_area(area_id)
    try:
        geometry = city_service().geometry()
    except (psycopg.Error, OSError, ValueError, KeyError) as error:
        raise HTTPException(status_code=503, detail="Boundary unavailable") from error
    if geometry["revision"] != revision:
        raise HTTPException(status_code=404, detail="Unknown boundary revision")
    return geometry


@router.get("/api/v1/fixture/captures/{capture_id}")
def fixture_evidence(
    capture_id: str,
    seconds: int = Query(default=0, ge=0, le=MAX_SECONDS),
    scenario: Scenario = Scenario.JOURNEY,
) -> dict[str, Any]:
    try:
        return city_service().evidence(capture_id, seconds, scenario)
    except CaptureNotFoundError as error:
        raise HTTPException(status_code=404, detail="Unknown fixture capture") from error
    except (psycopg.Error, OSError, ValueError, KeyError) as error:
        raise HTTPException(status_code=503, detail="Fixture evidence unavailable") from error

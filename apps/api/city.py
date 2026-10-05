"""Read-only fixture city endpoints; every clock is explicit and request-local."""

import json
from functools import lru_cache
from typing import Any

import psycopg
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError

from urbanpulse.adapters.city_store import CityInputStore, engine_for
from urbanpulse.adapters.postgis import PostgisMembership
from urbanpulse.application.city import AREA_ID, MAX_SECONDS, CaptureNotFoundError, CityService
from urbanpulse.application.composition import ComposedCityService
from urbanpulse.application.scenarios import Scenario
from urbanpulse.config import Settings

router = APIRouter()


@lru_cache(maxsize=1)
def input_store() -> CityInputStore:
    return CityInputStore(engine_for(Settings().database_url))


def city_service() -> ComposedCityService:
    settings = Settings()
    pointer = json.loads(
        (settings.city_capture_path / "current-import.json").read_text(encoding="utf-8")
    )
    if not isinstance(pointer, dict) or not isinstance(pointer.get("scope"), str):
        raise ValueError("invalid fixture import pointer; rerun fixture import")
    inputs = input_store().load(pointer["scope"])
    city = CityService(inputs, PostgisMembership(settings.database_url), inputs=inputs)
    return ComposedCityService(city, inputs)


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
    except (psycopg.Error, SQLAlchemyError, OSError, ValueError, KeyError) as error:
        raise HTTPException(
            status_code=503,
            detail="City snapshot unavailable; check services, migrations and fixture import",
        ) from error


@router.get("/api/v1/areas/{area_id}/boundaries/{revision}")
def area_boundary(area_id: str, revision: str) -> dict[str, Any]:
    require_area(area_id)
    try:
        geometry = city_service().geometry()
    except (psycopg.Error, SQLAlchemyError, OSError, ValueError, KeyError) as error:
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
    except (psycopg.Error, SQLAlchemyError, OSError, ValueError, KeyError) as error:
        raise HTTPException(status_code=503, detail="Fixture evidence unavailable") from error

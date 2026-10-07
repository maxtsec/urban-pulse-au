"""Read-only fixture city endpoints; every clock is explicit and request-local."""

from typing import Any, cast

import psycopg
from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy.exc import SQLAlchemyError

from apps.api.database import ApiDatabase
from apps.api.view_encoding import encode_view
from urbanpulse.adapters.city_store import CityInputStore
from urbanpulse.adapters.postgis import PostgisMembership
from urbanpulse.application.city import AREA_ID, MAX_SECONDS, CaptureNotFoundError, CityService
from urbanpulse.application.composition import ComposedCityService
from urbanpulse.application.scenarios import Scenario

router = APIRouter()


def input_store(request: Request) -> CityInputStore:
    return cast(ApiDatabase, request.app.state.database).inputs


def spatial_membership(request: Request) -> PostgisMembership:
    return cast(ApiDatabase, request.app.state.database).spatial


def city_service(request: Request) -> ComposedCityService:
    store = input_store(request)
    scope = store.active_scope()
    inputs = store.load(scope)
    city = CityService(inputs, spatial_membership(request), inputs=inputs)
    return ComposedCityService(city, inputs)


def require_area(area_id: str) -> None:
    if area_id != AREA_ID:
        raise HTTPException(status_code=404, detail="Unknown area")


@router.get("/api/v1/areas/{area_id}")
def area_snapshot(
    area_id: str,
    request: Request,
    seconds: int = Query(default=0, ge=0, le=MAX_SECONDS),
    scenario: Scenario = Scenario.JOURNEY,
) -> dict[str, Any]:
    require_area(area_id)
    try:
        return encode_view(city_service(request).snapshot(seconds, scenario))
    except (psycopg.Error, SQLAlchemyError, OSError, ValueError, KeyError) as error:
        raise HTTPException(
            status_code=503,
            detail="City snapshot unavailable; check services, migrations and fixture import",
        ) from error


@router.get("/api/v1/areas/{area_id}/boundaries/{revision}")
def area_boundary(area_id: str, revision: str, request: Request) -> dict[str, Any]:
    require_area(area_id)
    try:
        geometry = city_service(request).geometry()
    except (psycopg.Error, SQLAlchemyError, OSError, ValueError, KeyError) as error:
        raise HTTPException(status_code=503, detail="Boundary unavailable") from error
    if geometry["revision"] != revision:
        raise HTTPException(status_code=404, detail="Unknown boundary revision")
    return geometry


@router.get("/api/v1/fixture/captures/{capture_id}")
def fixture_evidence(
    capture_id: str,
    request: Request,
    seconds: int = Query(default=0, ge=0, le=MAX_SECONDS),
    scenario: Scenario = Scenario.JOURNEY,
) -> dict[str, Any]:
    try:
        return city_service(request).evidence(capture_id, seconds, scenario)
    except CaptureNotFoundError as error:
        raise HTTPException(status_code=404, detail="Unknown fixture capture") from error
    except (psycopg.Error, SQLAlchemyError, OSError, ValueError, KeyError) as error:
        raise HTTPException(status_code=503, detail="Fixture evidence unavailable") from error

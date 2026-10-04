"""Read-only fixture city endpoints; every clock is explicit and request-local."""

from functools import lru_cache
from typing import Any

import psycopg
from fastapi import APIRouter, HTTPException, Query

from urbanpulse.adapters.city_fixture import LocalCityCapture, capture_city
from urbanpulse.adapters.postgis import PostgisMembership
from urbanpulse.application.city import AREA_ID, MAX_SECONDS, CityService
from urbanpulse.config import Settings

router = APIRouter()


@lru_cache(maxsize=1)
def city_service() -> CityService:
    settings = Settings()
    capture_id = capture_city(settings.city_capture_path)
    return CityService(
        LocalCityCapture(settings.city_capture_path, capture_id),
        PostgisMembership(settings.database_url),
    )


def require_area(area_id: str) -> None:
    if area_id != AREA_ID:
        raise HTTPException(status_code=404, detail="Unknown area")


@router.get("/api/v1/areas/{area_id}")
def area_snapshot(
    area_id: str,
    seconds: int = Query(default=0, ge=0, le=MAX_SECONDS),
    scenario: str = Query(default="journey", pattern="^(journey|empty|outage)$"),
) -> dict[str, Any]:
    require_area(area_id)
    try:
        return city_service().snapshot(seconds, scenario)
    except (psycopg.Error, OSError, ValueError) as error:
        raise HTTPException(
            status_code=503, detail="City snapshot unavailable; check local services"
        ) from error


@router.get("/api/v1/areas/{area_id}/boundaries/{revision}")
def area_boundary(area_id: str, revision: str) -> dict[str, Any]:
    require_area(area_id)
    try:
        geometry = city_service().geometry()
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=503, detail="Boundary unavailable") from error
    if geometry["revision"] != revision:
        raise HTTPException(status_code=404, detail="Unknown boundary revision")
    return geometry


@router.get("/api/v1/fixture/captures/{capture_id}")
def fixture_evidence(capture_id: str) -> dict[str, Any]:
    try:
        captured = city_service().capture.read()
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=503, detail="Fixture evidence unavailable") from error
    if captured.capture_id != capture_id:
        raise HTTPException(status_code=404, detail="Unknown fixture capture")
    return {
        "mode": "fixture",
        "capture_id": captured.capture_id,
        "description": "Retained synthetic scenario with an official open-data boundary",
        "scenario_start": captured.scenario["started_at"],
        "synthetic_capture_references": True,
        "events": [
            {
                "id": frame["event"]["id"],
                "at_seconds": frame["at_seconds"],
                "capture_ids": frame["event"]["data"]["provenance"]["capture_ids"],
            }
            for frame in captured.scenario["frames"]
        ],
        "boundary_attribution": captured.boundary["properties"],
    }

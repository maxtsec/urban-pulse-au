"""Local environment smoke API; fixture data is always explicitly labelled."""

import json
from typing import Any

import psycopg
from fastapi import FastAPI, HTTPException
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from apps.api.city import city_service, router
from urbanpulse.config import ROOT, Settings

app = FastAPI(title="UrbanPulse AU", version="0.1.0")
app.include_router(router)


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok", "mode": "fixture"}


@app.get("/health/ready")
def ready() -> dict[str, str]:
    settings = Settings()
    try:
        with psycopg.connect(settings.database_url, connect_timeout=3) as connection:
            connection.execute("SELECT PostGIS_Version()").fetchone()
        with Redis.from_url(
            settings.redis_url, socket_connect_timeout=3, socket_timeout=3
        ) as cache:
            cache.ping()
    except (psycopg.Error, OSError) as exc:
        raise HTTPException(status_code=503, detail="PostGIS is unavailable") from exc
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Local dependencies are unavailable") from exc
    try:
        city_service()
    except (SQLAlchemyError, OSError, ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=503, detail="City inputs unavailable; run migrations and fixture import"
        ) from exc
    return {"status": "ok", "postgis": "ok", "redis": "ok", "city_inputs": "ok", "mode": "fixture"}


@app.get("/api/v1/fixture")
def fixture() -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(
        (ROOT / "tests/fixtures/transport.json").read_text(encoding="utf-8")
    )
    return payload

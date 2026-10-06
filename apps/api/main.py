"""Local environment smoke API; fixture data is always explicitly labelled."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast

import psycopg
from fastapi import FastAPI, HTTPException, Request
from pydantic import ValidationError
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from apps.api.city import router
from apps.api.database import ApiDatabase
from urbanpulse.config import ROOT, Settings


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    try:
        application.state.settings = Settings()
        application.state.database = ApiDatabase(application.state.settings.database_url)
    except (ValidationError, SQLAlchemyError, ValueError):
        # ValidationError text includes input values, which may contain credentials.
        raise RuntimeError(
            "Invalid application configuration; check environment settings"
        ) from None
    try:
        yield
    finally:
        application.state.database.close()


app = FastAPI(title="UrbanPulse AU", version="0.1.0", lifespan=lifespan)
app.include_router(router)


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok", "mode": "fixture"}


@app.get("/health/ready")
def ready(request: Request) -> dict[str, str]:
    settings = cast(Settings, request.app.state.settings)
    try:
        cast(ApiDatabase, request.app.state.database).probe()
    except (psycopg.Error, SQLAlchemyError, OSError) as exc:
        raise HTTPException(status_code=503, detail="PostGIS is unavailable") from exc
    if settings.cache_enabled:
        try:
            with Redis.from_url(
                settings.redis_url, socket_connect_timeout=3, socket_timeout=3
            ) as cache:
                cache.ping()
        except (RedisError, OSError) as exc:
            raise HTTPException(
                status_code=503, detail="Local dependencies are unavailable"
            ) from exc
    return {
        "status": "ok",
        "postgis": "ok",
        "redis": "ok" if settings.cache_enabled else "disabled",
        "mode": "fixture",
    }


@app.get("/api/v1/fixture")
def fixture() -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(
        (ROOT / "tests/fixtures/transport.json").read_text(encoding="utf-8")
    )
    return payload

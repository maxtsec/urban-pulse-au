"""Local environment smoke API; fixture data is always explicitly labelled."""

import json
from pathlib import Path
from typing import Any

import psycopg
from fastapi import FastAPI, HTTPException
from pydantic_settings import BaseSettings, SettingsConfigDict
from redis import Redis
from redis.exceptions import RedisError

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    database_url: str = "postgresql://urbanpulse:urbanpulse_local@127.0.0.1:5432/urbanpulse"
    redis_url: str = "redis://127.0.0.1:6379/0"


app = FastAPI(title="UrbanPulse AU", version="0.1.0")


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
    return {"status": "ok", "postgis": "ok", "redis": "ok", "mode": "fixture"}


@app.get("/api/v1/fixture")
def fixture() -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(
        (ROOT / "tests/fixtures/transport.json").read_text(encoding="utf-8")
    )
    return payload

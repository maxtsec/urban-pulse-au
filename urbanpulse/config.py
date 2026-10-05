"""Shared local configuration; entry points do not own workspace paths."""

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    urbanpulse_mode: Literal["fixture"] = "fixture"
    database_url: str = "postgresql://urbanpulse:urbanpulse_local@127.0.0.1:5432/urbanpulse"
    cache_enabled: bool = True
    redis_url: str = "redis://127.0.0.1:6379/0"
    raw_storage_path: Path = ROOT / ".local/raw"

    @property
    def city_capture_path(self) -> Path:
        return ROOT / self.raw_storage_path / "city"

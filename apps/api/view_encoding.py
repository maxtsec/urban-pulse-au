"""Canonical timestamps at the HTTP view boundary, without changing stored events."""

from datetime import UTC, datetime
from typing import Any, cast

from fastapi.encoders import jsonable_encoder


def utc_timestamp(value: datetime) -> str:
    if value.utcoffset() is None:
        raise ValueError("View timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat().removesuffix("+00:00") + "Z"


def encode_view(view: dict[str, Any]) -> dict[str, Any]:
    encoded = cast(dict[str, Any], jsonable_encoder(view, custom_encoder={datetime: utc_timestamp}))
    # Retained frame times enter these view fields as strings. Convert only the
    # declared fields, never arbitrary text or embedded capture evidence.
    weather = encoded.get("weather")
    if weather is not None:
        canonical_fields(weather, ("last_feed_update_received_at", "source_generated_at"))
        if weather.get("reading") is not None:
            canonical_fields(weather["reading"], ("received_at",))
    planning = encoded.get("planning")
    if planning is not None:
        canonical_fields(planning, ("last_successful_received_at",))
    return encoded


def canonical_fields(view: dict[str, Any], names: tuple[str, ...]) -> None:
    for name in names:
        value = view.get(name)
        if value is not None:
            view[name] = utc_timestamp(datetime.fromisoformat(value))

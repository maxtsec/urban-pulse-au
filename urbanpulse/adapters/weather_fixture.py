"""Normalize authored weather records, not a live provider's wire schema."""

from typing import Any

from urbanpulse.contracts.weather import ModelledReadingChanged, WeatherWarningChanged


def warning_event(raw: dict[str, Any], capture: dict[str, Any]) -> WeatherWarningChanged:
    subject = f"vicemergency/{raw['product']}/{raw['record_id']}"
    return WeatherWarningChanged.model_validate(
        {
            "specversion": "1.0",
            "id": raw["change_id"],
            "source": "urn:urbanpulse:fixture:weather",
            "type": "au.urbanpulse.weather.warning-changed.v1",
            "subject": subject,
            "time": capture["received_at"],
            "datacontenttype": "application/json",
            "upmode": "fixture",
            "data": {
                "schema_version": "1.0",
                "revision": raw["revision"],
                "provenance": {
                    "provider": "vicemergency",
                    "product": raw["product"],
                    "record_id": raw["record_id"],
                    "capture_ids": [capture["id"]],
                    "source_observed_at": raw["updated_at"],
                },
                "effective_from": raw["effective_from"],
                "effective_until": raw["effective_until"],
                "correlation_id": "synthetic-city-weather",
                "causation_id": None,
                "state": {
                    "warning_id": subject,
                    **{
                        key: raw[key]
                        for key in (
                            "level",
                            "headline",
                            "description",
                            "issued_at",
                            "updated_at",
                            "cancelled_at",
                            "geometry",
                            "spatial_precision",
                            "source_url",
                        )
                    },
                },
            },
        }
    )


def reading_event(raw: dict[str, Any]) -> ModelledReadingChanged:
    return ModelledReadingChanged.model_validate(
        {
            "specversion": "1.0",
            "id": raw["id"],
            "source": "urn:urbanpulse:fixture:weather",
            "type": "au.urbanpulse.weather.modelled-reading-changed.v1",
            "subject": raw["state"]["reading_id"],
            "time": raw["received_at"],
            "datacontenttype": "application/json",
            "upmode": "fixture",
            "data": {
                "schema_version": "1.0",
                "revision": raw["revision"],
                "provenance": {
                    "provider": "open-meteo",
                    "product": "modelled-weather",
                    "record_id": raw["record_id"],
                    "capture_ids": [raw["capture_id"]],
                    "source_observed_at": raw["state"]["valid_at"],
                },
                "effective_from": raw["state"]["valid_at"],
                "effective_until": None,
                "correlation_id": "synthetic-city-weather",
                "causation_id": None,
                "state": raw["state"],
            },
        }
    )


class FixtureWeatherNormalizer:
    warning = staticmethod(warning_event)
    reading = staticmethod(reading_event)

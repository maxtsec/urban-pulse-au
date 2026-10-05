"""Publish fixture service observations without leaking a future clearing frame."""

from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Any

from urbanpulse.application.city_replay import ServiceFrame
from urbanpulse.contracts.composition import TransportServiceStatusChanged


def service_events(
    frames: Iterable[ServiceFrame], started_at: datetime, stop: dict[str, Any]
) -> tuple[TransportServiceStatusChanged, ...]:
    events = []
    episode_id = None
    started = None
    for revision, frame in enumerate(frames, 1):
        at = started_at + timedelta(seconds=frame.at_seconds)
        if frame.status == "disrupted" and episode_id is None:
            episode_id, started = frame.id, at
        resolved = at if frame.status == "clear" and episode_id is not None else None
        events.append(
            TransportServiceStatusChanged.model_validate(
                {
                    "specversion": "1.0",
                    "id": frame.id,
                    "source": "urn:urbanpulse:fixture:transport",
                    "type": "au.urbanpulse.transport.service-status-changed.v1",
                    "subject": f"service/{frame.stop_id}",
                    "time": at,
                    "datacontenttype": "application/json",
                    "upmode": "fixture",
                    "data": {
                        "schema_version": "1.0",
                        "revision": revision,
                        "provenance": {
                            "provider": "synthetic",
                            "product": "tram-service",
                            "record_id": frame.stop_id,
                            "capture_ids": frame.capture_ids,
                            "source_observed_at": at,
                        },
                        "effective_from": at,
                        "effective_until": None,
                        "correlation_id": "synthetic-city",
                        "causation_id": None,
                        "state": {
                            "service_id": f"service/{frame.stop_id}",
                            "stop_id": frame.stop_id,
                            "position": {
                                "longitude": stop["coordinates"][0],
                                "latitude": stop["coordinates"][1],
                            },
                            "status": frame.status,
                            "episode_id": episode_id,
                            "started_at": started,
                            "observed_at": at,
                            "resolved_at": resolved,
                            "reason": frame.reason,
                        },
                    },
                }
            )
        )
        if frame.status == "clear":
            episode_id, started = None, None
    return tuple(events)

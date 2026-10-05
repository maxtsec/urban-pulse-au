"""Publish coverage independently of warning/position content changes."""

from datetime import datetime, timedelta
from typing import Any

from urbanpulse.application.delivery import ProjectionHandler, Publisher, revision_result
from urbanpulse.contracts.composition import SourceCoverageChanged
from urbanpulse.contracts.weather import PRODUCTS
from urbanpulse.location.published import PublishedProjection


def publish_coverage(
    publisher: Publisher, timeline: str, at: datetime, seconds: int, values: list[dict[str, Any]]
) -> list[SourceCoverageChanged]:
    handler = ProjectionHandler(
        "location.coverage",
        PublishedProjection(),
        SourceCoverageChanged.model_validate_json,
        PublishedProjection.consume,
    )
    events = []
    for item in values:
        owner = item["owner"]
        input_id = item["input_id"]
        observed_seconds = item["observed_seconds"]
        observed_at = at + timedelta(seconds=observed_seconds - seconds)
        event = SourceCoverageChanged.model_validate(
            {
                "specversion": "1.0",
                "id": f"coverage-{timeline}-{input_id}-{observed_seconds}",
                "source": f"urn:urbanpulse:fixture:{owner}",
                "type": f"au.urbanpulse.{owner}.coverage-changed.v1",
                "subject": f"coverage/{input_id}/{timeline}",
                "time": observed_at,
                "datacontenttype": "application/json",
                "upmode": "fixture",
                "data": {
                    "schema_version": "1.0",
                    "revision": observed_seconds + 1,
                    "provenance": {
                        "provider": "synthetic",
                        "product": input_id,
                        "record_id": timeline,
                        "capture_ids": item["capture_ids"],
                        "source_observed_at": None,
                    },
                    "effective_from": observed_at,
                    "effective_until": None,
                    "correlation_id": timeline,
                    "causation_id": None,
                    "state": {
                        "timeline_id": timeline,
                        "observation_id": item["observation_id"],
                        "input_id": input_id,
                        "state": item["state"],
                        "last_successful_received_at": item["received_at"],
                        "complete": item["state"] == "current",
                        "products": sorted(PRODUCTS) if owner == "weather" else [input_id],
                        "input_revisions": item["revisions"],
                    },
                },
            }
        )
        revision_result(publisher.publish(event.model_dump_json(), (handler,))[handler.name])
        events.append(
            SourceCoverageChanged.model_validate(
                handler.state.events[(event.source, event.subject)].model_dump()
            )
        )
    return events

"""Reconstruct deterministic area transitions on the bounded fixture clock."""

import math
from datetime import datetime
from typing import Any

from urbanpulse.application.capture_replay import payload_hash
from urbanpulse.application.city import CityService
from urbanpulse.application.delivery import ProjectionHandler, revision_result
from urbanpulse.application.inputs import CityInputs
from urbanpulse.contracts.composition import AreaStatusChanged
from urbanpulse.location.published import PublishedProjection


def transition_clocks(inputs: CityInputs, seconds: int) -> list[int]:
    captured = inputs.captured
    clocks = {0, seconds, captured.scenario["outage_at_seconds"]}
    clocks.update(frame["at_seconds"] for frame in captured.scenario["frames"])
    clocks.update(frame["at_seconds"] for frame in captured.scenario["service_frames"])
    started = datetime.fromisoformat(captured.scenario["started_at"])
    for step in inputs.weather:
        clocks.add(step.frame["at_seconds"])
        for event in step.events:
            for timestamp in (event.data.effective_from, event.data.effective_until):
                if timestamp is not None:
                    clocks.add(math.ceil((timestamp - started).total_seconds()))
    clocks.update(step.frame["at_seconds"] for step in inputs.planning)
    for bundle in (captured.weather, captured.planning):
        if bundle:
            clocks.add(bundle["outage_at_seconds"])
    return sorted(clock for clock in clocks if 0 <= clock <= seconds)


def semantic_state(snapshot: dict[str, Any]) -> dict[str, Any]:
    assessment = snapshot["assessment"]
    return {
        "condition": assessment["condition"],
        "reasons": assessment["reasons"],
        "coverage": [
            item
            for item in assessment["coverage"]
            if item["input_id"] in {"transport_service", "weather_warnings"}
        ],
    }


class ComposedCityService:
    def __init__(self, city: CityService, inputs: CityInputs) -> None:
        self.city = city
        self.inputs = inputs

    def geometry(self) -> dict[str, Any]:
        return self.city.geometry()

    def evidence(self, capture_id: str, seconds: int, scenario: str) -> dict[str, Any]:
        return self.city.evidence(capture_id, seconds, scenario)

    def snapshot(self, seconds: int, scenario: str = "journey") -> dict[str, Any]:
        # Validate the requested context before evaluating any earlier checkpoint.
        result = self.city.snapshot(seconds, scenario)
        timeline = result["composition"]["timeline_id"]
        publisher = self.city.publisher_factory(f"{timeline}:{seconds}:area")
        handler = ProjectionHandler(
            "location.area",
            PublishedProjection(),
            AreaStatusChanged.model_validate_json,
            PublishedProjection.consume,
        )
        transitions: list[dict[str, Any]] = []
        previous = None
        for clock in transition_clocks(self.inputs, seconds):
            view = result if clock == seconds else self.city.snapshot(clock, scenario)
            semantic = semantic_state(view)
            if semantic == previous:
                continue
            previous = semantic
            at = view["clock"]["at"]
            coverage = [
                event
                for event in view["composition"]["coverage_events"]
                if event["data"]["state"]["input_id"] in {"transport_service", "weather_warnings"}
            ]
            revisions = sorted(
                [
                    revision
                    for event in coverage
                    for revision in event["data"]["state"]["input_revisions"]
                ],
                key=lambda item: (item["source"], item["subject"]),
            )
            captures = sorted(
                {
                    capture
                    for event in coverage
                    for capture in event["data"]["provenance"]["capture_ids"]
                }
            )
            event = AreaStatusChanged.model_validate(
                {
                    "specversion": "1.0",
                    "id": payload_hash([timeline, clock, len(transitions) + 1]),
                    "source": "urn:urbanpulse:fixture:location",
                    "type": "au.urbanpulse.location.area-status-changed.v1",
                    "subject": f"{view['area']['id']}/{timeline}",
                    "time": at,
                    "datacontenttype": "application/json",
                    "upmode": "fixture",
                    "data": {
                        "schema_version": "1.0",
                        "revision": len(transitions) + 1,
                        "provenance": {
                            "provider": "synthetic",
                            "product": "area-condition",
                            "record_id": view["area"]["id"],
                            "capture_ids": captures,
                            "source_observed_at": None,
                        },
                        "effective_from": at,
                        "effective_until": None,
                        "correlation_id": timeline,
                        "causation_id": None,
                        "state": {
                            "timeline_id": timeline,
                            "area_id": view["area"]["id"],
                            "condition": semantic["condition"],
                            "reasons": semantic["reasons"],
                            "coverage": [item["data"]["state"] for item in coverage],
                            "boundary_revision": view["area"]["boundary_revision"],
                            "rule_version": view["policy_version"],
                            "input_revisions": revisions,
                            "evaluated_at": at,
                        },
                    },
                }
            )
            revision_result(publisher.publish(event.model_dump_json(), (handler,))[handler.name])
            transitions.append(event.model_dump(mode="json"))
        result["composition"]["area_events"] = transitions
        result["composition"]["recovery"] = "persisted-domain-inputs"
        return result

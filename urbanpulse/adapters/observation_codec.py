"""Versioned storage slots; frame/evidence values are opaque JSON, never event tags."""

from collections.abc import Callable
from typing import Any

from urbanpulse.contracts.events import CloudEvent

VERSION = 2
SLOTS = {"transport": ("event",), "weather": ("events", "warning_records"), "planning": ("event",)}


def map_event_slots(owner: str, row: object, convert: Callable[[Any], Any]) -> dict[str, Any]:
    if owner not in SLOTS or not isinstance(row, dict):
        raise ValueError("invalid observation event slots")
    result = dict(row)
    for slot in SLOTS[owner]:
        if slot not in row:
            raise ValueError("missing declared observation event slot")
        value = row[slot]
        if slot != "event":
            if not isinstance(value, (list, tuple)):
                raise ValueError("observation events must be a list")
            result[slot] = [convert(event) for event in value]
        else:
            result[slot] = None if value is None else convert(value)
    return result


def encode_observation(
    owner: str,
    row: dict[str, Any],
    reference: Callable[[CloudEvent[Any]], dict[str, Any]],
) -> dict[str, Any]:
    def convert(value: Any) -> dict[str, Any]:
        if not isinstance(value, CloudEvent):
            raise ValueError("declared event slot must contain a validated event")
        return reference(value)

    return map_event_slots(owner, row, convert)


def decode_observation(
    owner: str,
    version: int,
    row: object,
    resolve: Callable[[dict[str, Any]], CloudEvent[Any]],
) -> dict[str, Any]:
    if type(version) is not int or version != VERSION:
        raise ValueError("unsupported observation codec; run reviewed migrations")

    def convert(value: Any) -> CloudEvent[Any]:
        if not isinstance(value, dict):
            raise ValueError("invalid observation event descriptor")
        kind = value.get("kind")
        if kind == "reference":
            required = {"kind", "source", "id"}
            if not required <= value.keys() or value.keys() - required - {"attempt_envelope"}:
                raise ValueError("invalid observation reference fields")
            if not all(isinstance(value[key], str) and value[key] for key in ("source", "id")):
                raise ValueError("invalid observation reference identity")
            if "attempt_envelope" in value and not isinstance(value["attempt_envelope"], str):
                raise ValueError("invalid observation attempt envelope")
        elif kind == "rejected":
            if set(value) != {"kind", "envelope"} or not isinstance(value["envelope"], str):
                raise ValueError("invalid rejected observation envelope")
        else:
            raise ValueError("unknown observation event descriptor")
        return resolve(value)

    return map_event_slots(owner, row, convert)

"""Durable boundary validation remains independent of database and broker clients."""

import json
from pathlib import Path

import pytest

from urbanpulse.application.durable_delivery import receipt_from_wire, validate_key


@pytest.mark.parametrize(
    "value", ["", " has-space", "nul\x00", "x" * 201, "nonascii-\u00e9", 7, None]
)
def test_invalid_internal_context_or_consumer_key(value):
    with pytest.raises(ValueError):
        validate_key(value)


def test_storage_rejects_revisions_beyond_its_integer_range():
    value = json.loads(
        (Path(__file__).parents[1] / "fixtures/vehicle-position-event.json").read_text()
    )
    value["data"]["revision"] = 2**63
    with pytest.raises(ValueError, match="64-bit"):
        receipt_from_wire(json.dumps(value))


def test_durable_identity_ignores_delivery_trace_but_preserves_revision():
    value = json.loads(
        (Path(__file__).parents[1] / "fixtures/vehicle-position-event.json").read_text()
    )
    before = receipt_from_wire(json.dumps(value))
    value["traceparent"] = "00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01"
    assert receipt_from_wire(json.dumps(value)) == before
    value["data"]["revision"] += 1
    assert receipt_from_wire(json.dumps(value)) != before

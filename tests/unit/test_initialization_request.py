"""Reject unreviewed initialization targets before starting a child."""

import pytest

from urbanpulse.adapters.demo_database import EXPECTED_REVISION
from workers.initialization.job import InitializationRequest


@pytest.mark.parametrize(
    "override",
    [
        {"operation": "reset"},
        {"database": "postgres;drop"},
        {"expected_revision": "head"},
        {"role_prefix": "unsafe-role"},
        {"expected_import_id": "a" * 64},
        {"timeout_seconds": 0},
        {"timeout_seconds": 541},
        {"timeout_seconds": True},
    ],
)
def test_invalid_initialization_is_rejected(override):
    args = dict(operation="migrate", database="urbanpulse", expected_revision=EXPECTED_REVISION)
    with pytest.raises(ValueError):
        InitializationRequest(**(args | override))


def test_import_accepts_pinned_identity():
    request = InitializationRequest(
        "import", "urbanpulse", EXPECTED_REVISION, expected_import_id="a" * 64
    )
    assert request.expected_import_id == "a" * 64

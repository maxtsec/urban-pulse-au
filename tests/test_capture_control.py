"""Control schema invariants are portable; fsync/crash behavior is tested on Linux."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from urbanpulse.contracts.capture_control import MAX_SEQUENCE, Control, Summary
from urbanpulse.contracts.local_capture import Intent


def intent(sequence):
    return Intent(
        capture_id=uuid4(),
        capture_sequence=sequence,
        mode="fixture",
        provider="synthetic",
        product="vehicle-positions",
        requested_at=datetime.now(UTC),
        collector_version="test",
    )


@pytest.mark.parametrize("sequence", [0, -1, True, 1.5, MAX_SEQUENCE + 1])
def test_capture_sequence_is_positive_bounded_integer(sequence):
    with pytest.raises(ValidationError):
        intent(sequence)


@pytest.mark.parametrize(
    "values",
    [
        {"next_capture_sequence": 2},
        {"pending": intent(1)},
        {"pending": intent(2), "next_capture_sequence": 2, "generation": 1},
        {"pending": intent(1), "next_capture_sequence": 2, "generation": 2},
        {"generation": 1},
    ],
)
def test_sequence_and_generation_match_durable_accounting(values):
    with pytest.raises(ValidationError):
        Control(store_id=uuid4(), **values)


@pytest.mark.parametrize(
    "counts",
    [
        {"captured": True, "fetch-failed": 0, "raw-write-failed": 0, "abandoned": 0},
        {"captured": -1, "fetch-failed": 0, "raw-write-failed": 0, "abandoned": 0},
        {"captured": 1},
    ],
)
def test_summary_rejects_ambiguous_or_missing_counts(counts):
    with pytest.raises(ValidationError):
        Summary(outcomes=counts)


def test_unknown_summary_feed_does_not_expand_checkpoint():
    with pytest.raises(ValidationError):
        Summary(last_capture_at={"arbitrary": datetime.now(UTC)})

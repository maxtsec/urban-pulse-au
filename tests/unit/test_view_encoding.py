from datetime import UTC, datetime, timedelta, timezone

import pytest

from apps.api.view_encoding import encode_view, utc_timestamp


def test_view_encoding_preserves_microseconds_normalizes_offsets_and_leaves_evidence():
    instant = datetime(2026, 10, 7, 0, 0, 52, 750400, tzinfo=UTC)
    original = "2026-10-07T00:00:52.750400+00:00"
    view = {
        "nested": [{"observed_at": instant.astimezone(timezone(timedelta(hours=11)))}],
        "missing": None,
        "original_evidence": original,
    }
    encoded = encode_view(view)
    assert encoded["nested"][0]["observed_at"] == "2026-10-07T00:00:52.750400Z"
    assert encoded["missing"] is None
    assert encoded["original_evidence"] == original
    assert isinstance(view["nested"][0]["observed_at"], datetime)
    assert utc_timestamp(instant.replace(microsecond=0)) == "2026-10-07T00:00:52Z"


def test_naive_view_timestamp_is_not_assigned_the_hosts_timezone():
    with pytest.raises(ValueError, match="timezone-aware"):
        encode_view({"observed_at": datetime(2026, 10, 7)})


def test_retained_frame_times_are_canonical_only_in_declared_view_fields():
    source = "2026-10-07T11:00:52.750400+11:00"
    expected = "2026-10-07T00:00:52.750400Z"
    evidence = [{"received_at": source}]
    view = {
        "weather": {
            "reading": {"received_at": source},
            "last_feed_update_received_at": source,
            "source_generated_at": source,
            "evidence": evidence,
        },
        "planning": {"last_successful_received_at": source, "evidence": evidence},
    }
    encoded = encode_view(view)
    assert encoded["weather"]["reading"]["received_at"] == expected
    assert encoded["weather"]["last_feed_update_received_at"] == expected
    assert encoded["weather"]["source_generated_at"] == expected
    assert encoded["planning"]["last_successful_received_at"] == expected
    assert encoded["weather"]["evidence"] == evidence
    assert encoded["planning"]["evidence"] == evidence
    assert view["weather"]["reading"]["received_at"] == source
    assert encode_view({"weather": None, "planning": {"last_successful_received_at": None}}) == {
        "weather": None,
        "planning": {"last_successful_received_at": None},
    }

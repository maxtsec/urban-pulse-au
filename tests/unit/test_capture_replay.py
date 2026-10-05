import json
from datetime import datetime
from functools import partial

import pytest

from urbanpulse.adapters.planning_fixture import FixturePlanningNormalizer
from urbanpulse.adapters.weather_fixture import FixtureWeatherNormalizer
from urbanpulse.application.capture_replay import (
    CaptureHistory,
    capture_received_at,
    payload_hash,
    received_frames,
)
from urbanpulse.config import ROOT


@pytest.mark.parametrize("domain", ["planning", "weather"])
def test_shared_history_preserves_original_event_and_can_abandon_partial_capture(domain):
    bundle = json.loads((ROOT / f"tests/fixtures/{domain}-scenario.json").read_text())
    if domain == "planning":
        frame = bundle["frames"][0]
        raw = bundle["payloads"]["initial"]
        normalize = FixturePlanningNormalizer().snapshot
    else:
        frame = bundle["frames"][1]
        raw = bundle["payloads"]["advice"][0]
        normalize = FixtureWeatherNormalizer().warning
    history = CaptureHistory()
    digest = payload_hash(raw)
    abandoned = history.prepare(digest, partial(normalize, raw, frame))
    with pytest.raises(KeyError):
        history.redeliver(abandoned[1].id)
    # A failed later row abandons the attempt; a later successful capture owns provenance.
    later = {**frame, "id": "later-valid-capture", "received_at": "2026-10-04T00:10:00Z"}
    accepted = history.prepare(digest, partial(normalize, raw, later))
    assert accepted[1].data.provenance.capture_ids == (later["id"],)
    assert history.commit([accepted]) == (accepted[1],)
    replay = history.prepare(digest, lambda: pytest.fail("recapture must reuse original event"))
    assert history.commit([replay]) == ()
    assert replay[1] is history.redeliver(accepted[1].id)
    assert replay[1].time == accepted[1].time


def test_shared_timing_sorts_hides_future_and_blocks_outage_boundary():
    bundle = {"outage_at_seconds": 30, "frames": [{"at_seconds": s} for s in (60, 0, 30)]}
    assert [f["at_seconds"] for f in received_frames(bundle, 30, False)] == [0, 30]
    assert [f["at_seconds"] for f in received_frames(bundle, 60, True)] == [0]
    at = datetime.fromisoformat("2026-10-04T00:01:00+00:00")
    frame = {"at_seconds": 30, "received_at": "2026-10-04T00:00:30Z"}
    assert capture_received_at(frame, 60, at).second == 30
    with pytest.raises(ValueError, match="replay clock"):
        capture_received_at({**frame, "received_at": "2026-10-04T00:00:31Z"}, 60, at)

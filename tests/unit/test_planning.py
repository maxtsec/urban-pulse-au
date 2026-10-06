import copy

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from apps.api.main import app
from urbanpulse.adapters.city_fixture import LocalCityCapture, capture_city
from urbanpulse.adapters.planning_fixture import FixturePlanningNormalizer
from urbanpulse.adapters.weather_fixture import FixtureWeatherNormalizer
from urbanpulse.application.city import AREA_ID, CityService
from urbanpulse.contracts.planning import PlanningSnapshotPublished
from urbanpulse.location.planning import PlanningProjection


class Capture:
    def __init__(self, value):
        self.value = value

    def read(self):
        return self.value


class Spatial:
    def covers(self, geometry, points):
        return [lat < -37.81 for lon, lat in points]

    def overlaps(self, area, warning):
        return True


@pytest.fixture
def captured(tmp_path):
    return LocalCityCapture(tmp_path, capture_city(tmp_path)).read()


def city(captured, spatial=None):
    return CityService(
        Capture(captured),
        spatial or Spatial(),
        FixtureWeatherNormalizer(),
        FixturePlanningNormalizer(),
    )


def event(captured, payload="initial", frame=0):
    return FixturePlanningNormalizer().snapshot(
        captured.planning["payloads"][payload], captured.planning["frames"][frame]
    )


@pytest.mark.parametrize(
    "seconds,state,count,unlocated,removed",
    [
        (0, "current", 3, 0, 0),
        (90, "current", 3, 0, 0),
        (120, "unknown", 3, 0, 0),
        (150, "unknown", 2, 1, 1),
        (180, "unknown", 2, 1, 1),
        (210, "stale", 2, 1, 1),
        (240, "error", 2, 1, 1),
        (270, "current", 3, 0, 1),
        (360, "current", 3, 0, 1),
    ],
)
def test_planning_timeline_retains_profile_with_explicit_coverage(
    captured, seconds, state, count, unlocated, removed
):
    profile = city(captured).snapshot(seconds, "city")["planning"]
    assert profile["state"] == state
    assert len(profile["records"]) == count
    assert len(profile["unlocated_records"]) == unlocated
    assert len(profile["removed_records"]) == removed
    assert all(r["development_key"] != "synthetic-outside" for r in profile["records"])


@pytest.mark.parametrize("seconds", [0, 30, 60, 120, 150, 180, 240, 270, 330, 360])
def test_planning_never_changes_current_conditions(captured, seconds):
    service = city(captured)
    baseline = service.snapshot(seconds, "weather")["assessment"]
    for scenario in ("city", "planning-outage"):
        assessed = service.snapshot(seconds, scenario)["assessment"]
        assert assessed["condition"] == baseline["condition"]
        assert assessed["reasons"] == baseline["reasons"]
        assert assessed["incomplete_inputs"] == baseline["incomplete_inputs"]


def test_partial_and_rejected_captures_do_not_change_snapshot_or_receipt(captured):
    service = city(captured)
    before, partial, complete, invalid = [
        service.snapshot(s, "city")["planning"] for s in (90, 120, 150, 180)
    ]
    assert before["records"] == partial["records"]
    assert before["last_successful_received_at"] == partial["last_successful_received_at"]
    assert partial["incomplete_captures"] == 1
    assert complete["records"] == invalid["records"]
    assert complete["last_successful_received_at"] == invalid["last_successful_received_at"]
    assert invalid["projection"]["rejected"] == 1
    assert complete["removed_records"][0]["status"] == "Approved"
    assert complete["removed_records"][0]["last_seen_as_of"].month == 9


def test_unchanged_recapture_advances_receipt_not_source_date_or_event(captured):
    service = city(captured)
    before, after = [service.snapshot(s, "city")["planning"] for s in (60, 90)]
    assert before["as_of"] == after["as_of"]
    assert before["last_successful_received_at"] != after["last_successful_received_at"]
    assert after["projection"]["duplicate"] == 1
    assert after["projection"]["apply"] == 1
    assert after["evidence"][-1]["event_ids"] == []
    assert after["snapshots"] == before["snapshots"]


@pytest.mark.parametrize("seconds", [120, 150, 270, 360])
def test_outage_cannot_learn_future_planning_changes(captured, seconds):
    profile = city(captured).snapshot(seconds, "planning-outage")["planning"]
    assert profile["state"] == "error"
    assert profile["snapshot_id"] == "synthetic-planning-snapshot-1"
    assert profile["removed_records"] == []
    assert all(e["at_seconds"] < 120 for e in profile["evidence"])


@pytest.mark.parametrize("invalid", [None, [], "invalid", 3, {}, True])
def test_non_object_or_missing_record_rejects_whole_snapshot(captured, invalid, monkeypatch):
    captured.planning["payloads"]["updated"]["records"].append(invalid)
    monkeypatch.setattr("apps.api.city.city_service", lambda request: city(captured))
    with TestClient(app) as client:
        response = client.get(f"/api/v1/areas/{AREA_ID}?scenario=city&seconds=150")
        assert response.status_code == 200
        snapshot = response.json()
        profile = snapshot["planning"]
        assert profile["snapshot_id"] == "synthetic-planning-snapshot-1"
        assert profile["removed_records"] == []
        assert profile["projection"]["rejected"] == 1
        evidence = client.get(snapshot["evidence_url"])
        assert evidence.status_code == 200
        assert any(e["kind"] == "planning-rejected-capture" for e in evidence.json()["events"])


def test_complete_empty_snapshot_differs_from_no_snapshot(captured):
    captured.planning["frames"] = []
    unknown = city(captured).snapshot(0, "city")["planning"]
    assert unknown["snapshot_id"] is None and unknown["state"] == "unknown"
    captured.planning["frames"] = [
        dict(
            kind="capture",
            id="empty",
            at_seconds=0,
            received_at="2026-10-04T00:00:00Z",
            payload_id="initial",
        )
    ]
    captured.planning["payloads"]["initial"]["records"] = []
    empty = city(captured).snapshot(0, "city")["planning"]
    assert empty["records"] == [] and empty["state"] == "current"
    assert empty["snapshot_id"] is not None


def test_unknown_source_date_stays_unknown(captured):
    captured.planning["payloads"]["initial"]["as_of"] = None
    profile = city(captured).snapshot(0, "city")["planning"]
    assert profile["state"] == "unknown" and profile["as_of"] is None
    assert len(profile["records"]) == 3


def test_projection_duplicate_old_conflict_and_snapshot_identity(captured):
    old, new = event(captured), event(captured, "updated", 4)
    projection = PlanningProjection()
    assert projection.consume(old) == "apply"
    assert projection.consume(new) == "apply"
    assert projection.consume(old) == "duplicate"
    changed = old.model_dump(mode="json")
    changed["data"]["state"]["records"][0]["status"] = "Changed old content"
    assert projection.consume(PlanningSnapshotPublished.model_validate(changed)) == "conflict"
    changed = new.model_dump(mode="json")
    changed["id"] = "other-event"
    changed["data"]["revision"] = 3
    changed["data"]["state"]["records"][0]["status"] = "Changed snapshot identity"
    assert projection.consume(PlanningSnapshotPublished.model_validate(changed)) == "conflict"
    assert projection.latest == new


def test_unseen_older_revision_is_superseded(captured):
    projection = PlanningProjection()
    assert projection.consume(event(captured, "updated", 4)) == "apply"
    assert projection.consume(event(captured)) == "superseded"


def test_higher_revision_cannot_roll_source_date_back(captured):
    projection = PlanningProjection()
    projection.consume(event(captured, "updated", 4))
    captured.planning["payloads"]["initial"]["revision"] = 5
    assert projection.consume(event(captured)) == "conflict"
    assert projection.latest.data.state.snapshot_id == "synthetic-planning-snapshot-2"


def test_record_order_has_no_semantic_effect(captured):
    initial = event(captured)
    captured.planning["payloads"]["initial"]["records"].reverse()
    projection = PlanningProjection()
    assert projection.consume(initial) == "apply"
    assert projection.consume(event(captured)) == "duplicate"


@pytest.mark.parametrize(
    "mutation",
    [
        "identity",
        "scope",
        "owner",
        "future",
        "provenance",
        "validity",
        "duplicate-key",
        "position",
        "year",
    ],
)
def test_contract_rejects_invalid_or_inconsistent_snapshot(captured, mutation):
    wire = event(captured).model_dump(mode="json")
    data = wire["data"]
    state = data["state"]
    if mutation == "identity":
        wire["subject"] = "other"
    if mutation == "scope":
        state["scope_id"] = "other"
    if mutation == "owner":
        wire["source"] = "urn:urbanpulse:fixture:weather"
    if mutation == "future":
        state["as_of"] = data["provenance"]["source_observed_at"] = "2026-10-05T00:00:00Z"
    if mutation == "provenance":
        data["provenance"]["capture_ids"] = []
    if mutation == "validity":
        data["effective_from"] = "2026-09-01T00:00:00Z"
    if mutation == "duplicate-key":
        state["records"].append(copy.deepcopy(state["records"][0]))
    if mutation == "position":
        state["records"][0]["position"]["longitude"] = 181
    if mutation == "year":
        state["records"][0]["year_completed"] = True
    with pytest.raises(ValidationError):
        PlanningSnapshotPublished.model_validate(wire)


def test_movement_recomputes_membership_without_inventing_removal(captured):
    captured.planning["payloads"]["updated"]["records"][0]["position"]["latitude"] = -37.8
    profile = city(captured).snapshot(150, "city")["planning"]
    assert not any(r["development_key"] == "synthetic-a" for r in profile["records"])
    assert not any(r["development_key"] == "synthetic-a" for r in profile["removed_records"])


def test_replay_restart_rewind_and_evidence_are_deterministic(captured, monkeypatch):
    service = city(captured)
    initial = service.snapshot(90, "city")
    service.snapshot(360, "city")
    assert service.snapshot(90, "city") == initial == city(captured).snapshot(90, "city")
    expected = service.snapshot(270, "city")["planning"]["evidence"]
    monkeypatch.setattr(
        PlanningProjection, "consume", lambda *a: pytest.fail("projection on evidence path")
    )
    monkeypatch.setattr(
        service.spatial, "covers", lambda *a: pytest.fail("spatial call on evidence path")
    )
    records = service.evidence(captured.capture_id, 270, "city")["events"]
    ids = {r["id"] for r in expected}
    assert [r for r in records if r["id"] in ids] == expected
    assert all(r["at_seconds"] <= 270 for r in records)


def test_missing_bundle_reference_returns_503_and_unknown_capture_404(captured, monkeypatch):
    captured.planning["frames"][0]["payload_id"] = "private-missing"
    monkeypatch.setattr("apps.api.city.city_service", lambda request: city(captured))
    with TestClient(app) as client:
        for url in [f"/api/v1/areas/{AREA_ID}", f"/api/v1/fixture/captures/{captured.capture_id}"]:
            response = client.get(url + "?scenario=city&seconds=0")
            assert response.status_code == 503 and "private" not in response.text
        assert client.get("/api/v1/fixture/captures/missing?scenario=city").status_code == 404


def test_complete_empty_removes_prior_records_and_reappearance_restores_them(captured):
    captured.planning["payloads"]["updated"]["records"] = []
    empty = city(captured).snapshot(150, "city")["planning"]
    assert empty["records"] == [] and empty["state"] == "current"
    assert len(empty["removed_records"]) == 3
    captured.planning["payloads"]["recovered"]["records"] = copy.deepcopy(
        captured.planning["payloads"]["initial"]["records"]
    )
    restored = city(captured).snapshot(270, "city")["planning"]
    assert len(restored["records"]) == 3 and restored["removed_records"] == []
    assert len(restored["snapshots"]) == 3


@pytest.mark.parametrize("reported_area", ["Southbank", "Carlton", None])
def test_whole_fixture_location_gap_does_not_mean_capture_failed(captured, reported_area):
    captured.planning["payloads"]["updated"]["records"][-1]["clue_small_area"] = reported_area
    profile = city(captured).snapshot(150, "city")["planning"]
    assert profile["state"] == "unknown"
    assert profile["capture_state"] == "current"
    assert profile["snapshot_id"] == "synthetic-planning-snapshot-2"
    assert profile["last_successful_received_at"].endswith("00:02:30+00:00")
    assert len(profile["unlocated_records"]) == 1
    assert profile["unlocated_records"][0]["clue_small_area"] == reported_area


@pytest.mark.parametrize(
    "seconds,expected",
    [(120, "unknown"), (180, "unknown"), (210, "stale"), (240, "error"), (270, "current")],
)
def test_capture_state_tracks_acceptance_and_failures_independently(captured, seconds, expected):
    profile = city(captured).snapshot(seconds, "city")["planning"]
    assert profile["capture_state"] == expected


def test_planning_consumer_fingerprints_each_incoming_event_only_once(captured, monkeypatch):
    from urbanpulse.contracts.events import EventReceipt

    old, new = event(captured), event(captured, "updated", 4)
    original = EventReceipt.from_event
    calls = []

    def counted(cls, incoming):
        calls.append(incoming.id)
        return original(incoming)

    monkeypatch.setattr(EventReceipt, "from_event", classmethod(counted))
    projection = PlanningProjection()
    assert projection.consume(old) == "apply"
    assert projection.consume(new) == "apply"
    assert projection.consume(old) == "duplicate"
    assert calls == [old.id, new.id, old.id]
    assert projection.latest == new


def test_scenario_registry_api_snapshot_and_evidence_agree(captured, monkeypatch):
    from urbanpulse.application.scenarios import SCENARIOS, Scenario

    assert set(Scenario) == set(SCENARIOS)
    monkeypatch.setattr("apps.api.city.city_service", lambda request: city(captured))
    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()
        assert set(schema["components"]["schemas"]["Scenario"]["enum"]) == set(SCENARIOS)
        for scenario, policy in SCENARIOS.items():
            response = client.get(f"/api/v1/areas/{AREA_ID}?scenario={scenario}&seconds=150")
            assert response.status_code == 200
            snapshot = response.json()
            assert (snapshot["weather"] is not None) is policy.weather
            assert ("records" in snapshot["planning"]) is policy.planning
            evidence = client.get(snapshot["evidence_url"])
            assert evidence.status_code == 200
            kinds = {e["kind"] for e in evidence.json()["events"]}
            assert ("modelled-reading-capture" in kinds) is policy.weather
            assert ("planning-snapshot-capture" in kinds) is policy.planning
        for suffix in ("not-a-scenario", "city%0A"):
            assert client.get(f"/api/v1/areas/{AREA_ID}?scenario={suffix}").status_code == 422
            assert (
                client.get(
                    f"/api/v1/fixture/captures/{captured.capture_id}?scenario={suffix}"
                ).status_code
                == 422
            )

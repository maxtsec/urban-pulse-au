import copy
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from apps.api.main import app
from urbanpulse.adapters.city_fixture import LocalCityCapture, capture_city
from urbanpulse.adapters.weather_fixture import FixtureWeatherNormalizer, warning_event
from urbanpulse.application.city import AREA_ID, CityService
from urbanpulse.contracts.weather import WeatherWarningChanged
from urbanpulse.location.weather import WeatherProjection


class MemoryCapture:
    def __init__(self, captured):
        self.captured = captured

    def read(self):
        return self.captured


class Spatial:
    def covers(self, geometry, points):
        return [True] * len(points)

    def overlaps(self, area, warning):
        return True


@pytest.fixture
def captured(tmp_path):
    return LocalCityCapture(tmp_path, capture_city(tmp_path)).read()


def service(captured, spatial=None):
    return CityService(MemoryCapture(captured), spatial or Spatial(), FixtureWeatherNormalizer())


@pytest.mark.parametrize(
    "seconds,condition,coverage,level,lifecycle",
    [
        (0, "unknown", "unknown", None, None),
        (30, "normal", "current", "Advice", "active"),
        (60, "degraded", "current", "Watch and Act", "active"),
        (149, "degraded", "current", "Watch and Act", "active"),
        (150, "degraded", "current", "Watch and Act", "cancelled"),
        (180, "degraded", "current", "Emergency Warning", "active"),
        (239, "degraded", "stale", "Emergency Warning", "active"),
        (240, "unknown", "stale", "Emergency Warning", "expired"),
        (270, "normal", "current", "Emergency Warning", "expired"),
        (300, "unknown", "unknown", "Unrecognised level", "active"),
        (330, "unknown", "unknown", "Unrecognised level", "active"),
        (360, "unknown", "unknown", "Unrecognised level", "expired"),
    ],
)
def test_warning_timeline(captured, seconds, condition, coverage, level, lifecycle):
    result = service(captured).snapshot(seconds, "weather")
    assert result["assessment"]["condition"] == condition
    assert result["weather"]["coverage"] == coverage
    if level:
        assert any(
            w["level"] == level and w["lifecycle"] == lifecycle
            for w in result["weather"]["warnings"]
        )
    if seconds == 150:
        assert {r["input_id"] for r in result["assessment"]["reasons"]} == {"transport_service"}


def test_model_information_does_not_fill_warning_coverage_or_degrade(captured):
    first = service(captured).snapshot(0, "weather")
    assert first["weather"]["reading"]["kind"] == "modelled"
    assert first["assessment"]["condition"] == "unknown"
    assert first["assessment"]["reasons"] == ()
    captured.weather["readings"][0]["state"]["temperature_c"] = 60.0
    assert service(captured).snapshot(0, "weather")["assessment"] == first["assessment"]


def test_repeat_capture_advances_receipt_without_new_event_or_source_warning_time(captured):
    city = service(captured)
    before, after = [city.snapshot(s, "weather")["weather"] for s in (60, 120)]
    assert before["warnings"] == after["warnings"]
    assert before["last_feed_update_received_at"] != after["last_feed_update_received_at"]
    captures = [e for e in after["evidence"] if e["kind"] == "warning-capture"]
    assert captures[-1]["payload_sha256"] == captures[-2]["payload_sha256"]
    assert captures[-1]["event_ids"] == []
    assert after["projection"]["duplicate"] == 2
    assert before["projection"]["apply"] == after["projection"]["apply"]


@pytest.mark.parametrize(
    "seconds,condition,lifecycle",
    [
        (90, "degraded", "active"),
        (200, "degraded", "active"),
        (240, "unknown", "expired"),
        (360, "unknown", "expired"),
    ],
)
def test_outage_retains_known_warning_until_expiry_without_future_cancellation(
    captured, seconds, condition, lifecycle
):
    result = service(captured).snapshot(seconds, "weather-outage")
    weather = result["weather"]
    assert result["assessment"]["condition"] == condition
    assert weather["coverage"] == "error"
    assert weather["warnings"][0]["cancelled_at"] is None
    assert weather["warnings"][0]["lifecycle"] == lifecycle
    assert weather["last_feed_update_received_at"].endswith("00:01:00+00:00")
    assert all(e["at_seconds"] < 90 for e in weather["evidence"])


def test_replay_clock_is_isolated_and_evidence_does_not_leak_future(captured, monkeypatch):
    city = service(captured)
    monkeypatch.setattr("apps.api.city.city_service", lambda request: city)
    with TestClient(app) as client:
        initial = client.get(f"/api/v1/areas/{AREA_ID}?scenario=weather&seconds=30").json()
        client.get(f"/api/v1/areas/{AREA_ID}?scenario=weather&seconds=360")
        assert client.get(f"/api/v1/areas/{AREA_ID}?scenario=weather&seconds=30").json() == initial
        evidence = client.get(initial["evidence_url"]).json()
        assert all(e["at_seconds"] <= 30 for e in evidence["events"])
    assert initial["weather"]["warnings"][0]["level"] == "Advice"
    assert initial["weather"]["warnings"][0]["cancelled_at"] is None


def test_retained_capture_replay_requires_no_provider_or_fixture_file_reads(
    captured, tmp_path, monkeypatch
):
    import urllib.request

    retained = LocalCityCapture(tmp_path, capture_city(tmp_path))
    expected = service(captured).snapshot(180, "weather")
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("network access"))
    assert (
        CityService(retained, Spatial(), FixtureWeatherNormalizer()).snapshot(180, "weather")
        == expected
    )


@pytest.mark.parametrize("member", [False, None])
def test_outside_and_unknown_geography_do_not_create_area_facts(captured, member):
    class Membership(Spatial):
        def overlaps(self, area, warning):
            return member

    result = service(captured, Membership()).snapshot(180, "weather")
    assert result["assessment"]["condition"] == ("normal" if member is False else "unknown")
    assert result["assessment"]["reasons"] == ()


def test_unknown_severity_does_not_repair_itself_when_warning_expires(captured):
    for second in (330, 360):
        assert service(captured).snapshot(second, "weather")["weather"]["coverage"] == "unknown"


def test_omission_from_complete_snapshot_does_not_cancel_active_fact(captured):
    next(f for f in captured.weather["frames"] if f["at_seconds"] == 150)["payload_id"] = "empty"
    result = service(captured).snapshot(150, "weather")
    assert result["weather"]["coverage"] == "unknown"
    assert any(r["input_id"] == "weather_warnings" for r in result["assessment"]["reasons"])


def test_rejected_capture_does_not_advance_receipt_or_partially_apply(captured):
    bad = copy.deepcopy(captured.weather["payloads"]["watch"][0])
    bad["revision"] = 0
    captured.weather["payloads"]["cancel"].append(bad)
    result = service(captured).snapshot(150, "weather")["weather"]
    assert result["last_feed_update_received_at"].endswith("00:02:00+00:00")
    assert result["warnings"][0]["cancelled_at"] is None
    assert result["coverage"] == "unknown"
    assert result["projection"]["rejected"] == 1


def test_projection_guards_duplicates_older_conflicts_and_provider_scope(captured):
    bundle = captured.weather
    old = warning_event(bundle["payloads"]["advice"][0], bundle["frames"][1])
    new = warning_event(bundle["payloads"]["watch"][0], bundle["frames"][2])
    projection = WeatherProjection()
    assert projection.consume(new) == "apply"
    assert projection.consume(old) == "superseded"
    assert projection.consume(new) == "duplicate"
    changed = new.model_dump(mode="json")
    changed["data"]["state"]["headline"] = "Conflicting content"
    assert projection.consume(WeatherWarningChanged.model_validate(changed)) == "conflict"
    changed = old.model_dump(mode="json")
    changed["data"]["state"]["headline"] = "Changed older identity"
    assert projection.consume(WeatherWarningChanged.model_validate(changed)) == "conflict"
    views, facts, complete = projection.warnings(
        datetime.fromisoformat(new.time.isoformat()), {}, Spatial()
    )
    assert len(facts) == 1 and complete
    assert views[0]["headline"] == new.data.state.headline


@pytest.mark.parametrize(
    "mutation", ["subject", "interval", "cancel", "source-time", "geometry", "capture", "owner"]
)
def test_warning_contract_rejects_inconsistent_records(captured, mutation):
    bundle = captured.weather
    wire = warning_event(bundle["payloads"]["watch"][0], bundle["frames"][2]).model_dump(
        mode="json"
    )
    if mutation == "subject":
        wire["subject"] = "other"
    if mutation == "interval":
        wire["data"]["effective_until"] = wire["data"]["effective_from"]
    if mutation == "cancel":
        wire["data"]["state"]["cancelled_at"] = "2026-10-03T00:00:00Z"
    if mutation == "source-time":
        wire["data"]["provenance"]["source_observed_at"] = None
    if mutation == "geometry":
        wire["data"]["state"]["geometry"]["coordinates"][0][0] = [181, 1]
    if mutation == "capture":
        wire["data"]["provenance"]["capture_ids"] = []
    if mutation == "owner":
        wire["source"] = "urn:urbanpulse:fixture:transport"
    with pytest.raises(ValidationError):
        WeatherWarningChanged.model_validate(wire)


def test_same_severity_from_other_provider_has_no_approved_mapping(captured):
    bundle = captured.weather
    wire = warning_event(bundle["payloads"]["watch"][0], bundle["frames"][2]).model_dump(
        mode="json"
    )
    wire["data"]["provenance"]["provider"] = "bom"
    wire["subject"] = wire["data"]["state"]["warning_id"] = "bom/severe-thunderstorm/storm-1"
    projection = WeatherProjection()
    projection.consume(WeatherWarningChanged.model_validate(wire))
    _, facts, complete = projection.warnings(
        datetime.fromisoformat("2026-10-04T00:02:00+00:00"), {}, Spatial()
    )
    assert facts == () and not complete


@pytest.mark.parametrize("products", [[], ["severe-thunderstorm"], ["fire"]])
def test_partial_product_scope_cannot_claim_complete_warning_coverage(captured, products):
    captured.weather["frames"][1]["products"] = products
    assert service(captured).snapshot(30, "weather")["assessment"]["condition"] == "unknown"


def test_successful_empty_complete_snapshot_is_normal_only_with_transport_coverage(captured):
    captured.weather["frames"][0]["complete"] = True
    result = service(captured).snapshot(0, "weather")
    assert result["assessment"]["condition"] == "normal"
    assert result["weather"]["warnings"] == []


def test_unknown_geometry_keeps_known_adverse_facts_with_incomplete_coverage(captured):
    raw = copy.deepcopy(captured.weather["payloads"]["watch"][0])
    raw["record_id"] = "missing-shape"
    raw["change_id"] = "missing-shape-change"
    raw["geometry"] = None
    raw["spatial_precision"] = "unknown"
    captured.weather["payloads"]["watch"].append(raw)
    result = service(captured).snapshot(60, "weather")
    assert result["assessment"]["condition"] == "degraded"
    assert result["weather"]["coverage"] == "unknown"
    assert sum(r["input_id"] == "weather_warnings" for r in result["assessment"]["reasons"]) == 1


def test_weather_evidence_does_not_require_spatial_service_or_projections(captured, monkeypatch):
    import psycopg

    class Broken(Spatial):
        def overlaps(self, area, warning):
            raise psycopg.OperationalError("private details")

    city = service(captured, Broken())
    monkeypatch.setattr("apps.api.city.city_service", lambda request: city)
    with TestClient(app) as client:
        area = client.get(f"/api/v1/areas/{AREA_ID}?scenario=weather&seconds=60")
        assert area.status_code == 503 and "private" not in area.text
        monkeypatch.setattr(city, "snapshot", lambda *a, **k: pytest.fail("snapshot replay"))
        monkeypatch.setattr(
            "urbanpulse.location.city.PositionProjection.consume",
            lambda *a, **k: pytest.fail("transport projection"),
        )
        monkeypatch.setattr(
            WeatherProjection, "consume", lambda *a, **k: pytest.fail("weather projection")
        )
        response = client.get(
            f"/api/v1/fixture/captures/{captured.capture_id}?scenario=weather&seconds=60"
        )
    assert response.status_code == 200
    assert any(e["kind"] == "warning-capture" for e in response.json()["events"])


@pytest.mark.parametrize("field", ["reading_id", "kind", "temperature_c", "valid_at"])
def test_modelled_contract_rejects_identity_kind_numbers_and_future_time(captured, field):
    from urbanpulse.adapters.weather_fixture import reading_event

    raw = captured.weather["readings"][0]
    values = {
        "reading_id": "wrong-record",
        "kind": "station-observation",
        "temperature_c": float("nan"),
        "valid_at": "2026-10-04T00:10:00Z",
    }
    raw["state"][field] = values[field]
    with pytest.raises(ValidationError):
        reading_event(raw)


@pytest.mark.parametrize(
    "broken", ["payload-reference", "redelivery-reference", "transport-reference"]
)
def test_broken_fixture_references_are_503_but_unknown_capture_is_404(
    captured, monkeypatch, broken
):
    if broken == "payload-reference":
        captured.weather["frames"][0]["payload_id"] = "private-missing-payload"
    elif broken == "redelivery-reference":
        captured.weather["frames"][3]["event_id"] = "private-missing-event"
    else:
        del captured.scenario["service_stop"]
    monkeypatch.setattr("apps.api.city.city_service", lambda request: service(captured))
    with TestClient(app) as client:
        area = client.get(f"/api/v1/areas/{AREA_ID}?scenario=weather&seconds=120")
        evidence = client.get(
            f"/api/v1/fixture/captures/{captured.capture_id}?scenario=weather&seconds=120"
        )
        missing = client.get("/api/v1/fixture/captures/not-present?scenario=weather&seconds=120")
    assert area.status_code == evidence.status_code == 503
    assert "private" not in area.text and "private" not in evidence.text
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Unknown fixture capture"


def test_declared_extra_products_do_not_invalidate_complete_pilot_coverage(captured):
    captured.weather["frames"][1]["products"].append("additional-product")
    result = service(captured).snapshot(30, "weather")
    assert result["weather"]["coverage"] == "current"
    assert result["assessment"]["condition"] == "normal"


@pytest.mark.parametrize("scenario", ["weather", "weather-outage"])
@pytest.mark.parametrize("seconds", [0, 60, 120, 150, 360])
def test_dedicated_weather_evidence_matches_snapshot_and_replay_clock(captured, scenario, seconds):
    city = service(captured)
    expected = city.snapshot(seconds, scenario)["weather"]["evidence"]
    ids = {e["id"] for e in expected}
    records = city.evidence(captured.capture_id, seconds, scenario)["events"]
    actual = [e for e in records if e["id"] in ids]
    assert actual == sorted(expected, key=lambda e: (e["at_seconds"], e["id"]))
    assert all(e["at_seconds"] <= seconds for e in actual)


@pytest.mark.parametrize("invalid", [None, 1, "invalid", [], True])
@pytest.mark.parametrize("first", [False, True])
def test_non_object_warning_rejects_whole_capture_in_area_and_evidence(
    captured, monkeypatch, invalid, first
):
    records = captured.weather["payloads"]["cancel"]
    records.insert(0 if first else len(records), invalid)
    monkeypatch.setattr("apps.api.city.city_service", lambda request: service(captured))
    with TestClient(app) as client:
        response = client.get(f"/api/v1/areas/{AREA_ID}?scenario=weather&seconds=150")
        assert response.status_code == 200
        area = response.json()
        weather = area["weather"]
        assert weather["last_feed_update_received_at"].endswith("00:02:00+00:00")
        assert weather["warnings"][0]["cancelled_at"] is None
        assert weather["warnings"][0]["level"] == "Watch and Act"
        assert weather["coverage"] == "unknown"
        assert weather["projection"]["rejected"] == 1
        assert weather["projection"]["apply"] == 3
        evidence = client.get(area["evidence_url"])
        assert evidence.status_code == 200
        rejected = [e for e in evidence.json()["events"] if e["kind"] == "rejected-capture"]
        assert len(rejected) == 1 and rejected[0]["at_seconds"] == 150


@pytest.mark.parametrize("invalid", [None, {}, "invalid", 1])
def test_non_array_warning_payload_is_rejected(captured, invalid):
    captured.weather["payloads"]["cancel"] = invalid
    weather = service(captured).snapshot(150, "weather")["weather"]
    assert weather["projection"]["rejected"] == 1
    assert weather["last_feed_update_received_at"].endswith("00:02:00+00:00")
    assert weather["warnings"][0]["cancelled_at"] is None

"""Synthetic provider samples and an injected clock; tests never call upstream."""

import json
from pathlib import Path
from zipfile import ZipFile

import httpx
import pytest
from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2 as pb

from scripts import transport_probe as probe
from scripts.gtfs_probe import Schedule, decode, entity_fingerprint, positions, summarize


@pytest.fixture
def schedule(tmp_path: Path) -> Schedule:
    archive = tmp_path / "tram.zip"
    with ZipFile(archive, "w") as z:
        z.writestr(
            "trips.txt", "trip_id,route_id,service_id,shape_id,direction_id\nt,r,s,shape,0\n"
        )
        z.writestr("routes.txt", "route_id\nr\n")
        z.writestr("shapes.txt", "shape_id,shape_pt_sequence\nshape,1\nshape,2\n")
        z.writestr(
            "calendar.txt",
            "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\ns,1,1,1,1,1,0,0,20261001,20261031\n",
        )
        z.writestr(
            "calendar_dates.txt", "service_id,date,exception_type\ns,20261008,2\ns,20261101,1\n"
        )
    return Schedule.read(archive)


def sample() -> pb.FeedMessage:
    feed = pb.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = 1000
    v = feed.entity.add(id="entity-is-not-vehicle").vehicle
    v.vehicle.id = "vehicle"
    v.trip.trip_id = "t"
    v.trip.route_id = "r"
    v.trip.start_date = "20261007"
    v.position.latitude = -37.82
    v.position.longitude = 144.96
    v.timestamp = 900
    return feed


def test_exact_trip_route_shape_and_service_date(schedule: Schedule) -> None:
    trip = sample().entity[0].vehicle.trip
    assert schedule.linkage(trip) == "linked"
    trip.start_date = "20261008"
    assert schedule.linkage(trip) == "service_inactive"
    trip.start_date = "20261101"
    assert schedule.linkage(trip) == "linked"  # Added service overrides calendar range.
    trip.start_date = "20261102"
    assert schedule.linkage(trip) == "service_inactive"
    trip.ClearField("start_date")
    assert schedule.linkage(trip) == "service_date_missing"


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("trip_id", "prefix-t", "trip_not_found"),
        ("trip_id", "", "missing_trip_id"),
        ("route_id", "different", "route_mismatch"),
        ("direction_id", 1, "direction_mismatch"),
        ("start_date", "20260230", "service_date_invalid"),
        ("schedule_relationship", pb.TripDescriptor.CANCELED, "non_scheduled"),
    ],
)
def test_linkage_does_not_guess(
    schedule: Schedule, field: str, value: object, expected: str
) -> None:
    trip = sample().entity[0].vehicle.trip
    setattr(trip, field, value)
    assert schedule.linkage(trip) == expected


def test_ambiguous_static_and_frequency_instance(schedule: Schedule) -> None:
    trip = sample().entity[0].vehicle.trip
    schedule.frequency_trips.add("t")
    assert schedule.linkage(trip) == "frequency_instance_unverified"
    schedule.trips["t"].append(schedule.trips["t"][0].copy())
    assert schedule.linkage(trip) == "ambiguous_trip_id"


def test_missing_shape_and_calendar_do_not_match(schedule: Schedule) -> None:
    trip = sample().entity[0].vehicle.trip
    schedule.calendars.clear()
    assert schedule.linkage(trip) == "service_date_unverified"
    schedule.shapes.clear()
    assert schedule.linkage(trip) == "shape_missing"


def test_absence_is_not_zero_or_receipt_time(schedule: Schedule) -> None:
    feed = sample()
    v = feed.entity[0].vehicle
    v.ClearField("timestamp")
    v.vehicle.ClearField("id")
    feed.header.ClearField("timestamp")
    result = summarize(feed, schedule, 1100)
    assert result["header_timestamp"] is None
    assert result["counts"]["missing_observed_at"] == 1
    assert result["counts"]["missing_vehicle_id"] == 1
    assert result["observation_age_seconds"]["max"] is None
    assert positions(feed) == {}


def test_receipt_does_not_refresh_source_time(schedule: Schedule) -> None:
    result = summarize(sample(), schedule, 1301)
    assert result["counts"]["observation_over_300s"] == 1
    assert result["observation_age_seconds"]["min"] == 401


def test_duplicate_vehicle_ids_excluded_from_motion() -> None:
    feed = sample()
    feed.entity.add().CopyFrom(feed.entity[0])
    assert positions(feed) == {}


@pytest.mark.parametrize("body", [b"", b"not protobuf"])
def test_invalid_wire_rejected(body: bytes) -> None:
    with pytest.raises((ValueError, DecodeError)):
        decode(body)


@pytest.mark.parametrize("duration,expected", [(60, 7), (120, 11)])
def test_budget(duration: int, expected: int) -> None:
    plan = probe.request_plan(duration)
    assert len(plan) == expected
    assert all(b[0] - a[0] >= 10 for a, b in zip(plan, plan[1:], strict=False))
    for start, _ in plan:
        assert sum(start <= t < start + 60 for t, _ in plan) <= 6
    with pytest.raises(ValueError):
        probe.request_plan(3600)


class Clock:
    now = 0.0

    def sleep(self, seconds: float) -> None:
        self.now += seconds

    def read(self) -> float:
        return self.now


def test_finite_probe_hashes_duplicates_and_motion(tmp_path: Path, schedule: Schedule) -> None:
    requests = []
    clock = Clock()
    body = sample().SerializeToString()

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((clock.now, request))
        return httpx.Response(200, stream=httpx.ByteStream(body))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        report = probe.run_probe(
            client,
            schedule,
            "test-secret",
            "KeyID",
            tmp_path,
            60,
            sleep=clock.sleep,
            monotonic=clock.read,
        )
    assert len(requests) == 7
    assert report["captures"][3]["unchanged"] is True
    assert report["captures"][3]["position_comparison"] == {
        "shared_vehicles": 1,
        "coordinates_changed": 0,
        "coordinates_changed_same_observed_at": 0,
        "observation_time_changed": 0,
    }
    assert "test-secret" not in json.dumps(report)
    assert all(r.headers["KeyID"] == "test-secret" and not r.url.query for _, r in requests)
    assert len(list(tmp_path.glob("*.pb"))) == 7


@pytest.mark.parametrize("status", [401, 403, 429, 500, 302])
def test_error_stops_without_retry_redirect_or_body_retention(
    tmp_path: Path, schedule: Schedule, status: int
) -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            status, headers={"Location": "https://other.example"}, content=b"test-secret"
        )

    clock = Clock()
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        report = probe.run_probe(
            client,
            schedule,
            "test-secret",
            "KeyID",
            tmp_path,
            60,
            sleep=clock.sleep,
            monotonic=clock.read,
        )
    assert len(requests) == 1
    assert report["stopped"] == "http_error"
    assert "test-secret" not in (tmp_path / "report.json").read_text()
    assert not list(tmp_path.glob("*.pb"))


def test_oversized_and_encoded_responses_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(probe, "MAX_BYTES", 4)
    for headers, body in [({}, b"12345"), ({"Content-Encoding": "gzip"}, b"123")]:
        with httpx.Client(
            transport=httpx.MockTransport(
                lambda _, h=headers, b=body: httpx.Response(
                    200, headers=h, stream=httpx.ByteStream(b)
                )
            )
        ) as client:
            record, payload = probe.fetch(client, "vehicle-positions", "secret", "KeyID")
        assert payload is None
        assert record["error"] in {"response_limit", "unexpected_content_encoding"}


def test_network_error_redacted() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("secret-echo", request=request)

    with httpx.Client(transport=httpx.MockTransport(fail)) as client:
        record, body = probe.fetch(client, "vehicle-positions", "secret", "KeyID")
    assert body is None and record["error"] == "network_error"
    assert "secret" not in json.dumps(record)


def test_slow_requests_never_catch_up_in_burst(tmp_path: Path, schedule: Schedule) -> None:
    clock = Clock()
    starts = []

    def handler(_: httpx.Request) -> httpx.Response:
        starts.append(clock.now)
        clock.now += 45
        return httpx.Response(200, stream=httpx.ByteStream(sample().SerializeToString()))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        report = probe.run_probe(
            client,
            schedule,
            "secret",
            "KeyID",
            tmp_path,
            60,
            sleep=clock.sleep,
            monotonic=clock.read,
        )
    assert report["stopped"] == "session_deadline"
    assert all(b - a >= 10 for a, b in zip(starts, starts[1:], strict=False))


def test_invalid_capture_is_retained_and_rejected(tmp_path: Path, schedule: Schedule) -> None:
    clock = Clock()
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, stream=httpx.ByteStream(b"invalid"))
        )
    ) as client:
        report = probe.run_probe(
            client,
            schedule,
            "secret",
            "KeyID",
            tmp_path,
            60,
            sleep=clock.sleep,
            monotonic=clock.read,
        )
    assert report["stopped"] == "invalid_protobuf"
    assert len(report["captures"]) == 1
    assert (tmp_path / "01-vehicle-positions.pb").read_bytes() == b"invalid"


def test_cli_offline_uses_repo_relative_static_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, schedule: Schedule
) -> None:
    import sys

    monkeypatch.setattr(probe, "ROOT", tmp_path)
    monkeypatch.chdir(tmp_path.parent)
    monkeypatch.setattr(sys, "argv", ["probe", "--static-zip", "tram.zip"])

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Offline CLI must not construct HTTP client")

    monkeypatch.setattr(httpx, "Client", forbidden)
    assert probe.main() == 0


def test_cli_lock_blocks_live_request(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, schedule: Schedule
) -> None:
    import sys

    monkeypatch.setattr(probe, "PRIVATE", tmp_path)
    monkeypatch.setenv("DTP_OPENDATA_API_KEY", "synthetic-secret")
    monkeypatch.setattr(
        sys, "argv", ["probe", "--static-zip", str(tmp_path / "tram.zip"), "--live"]
    )
    (tmp_path / "probe.lock").write_text("synthetic-owner")
    with pytest.raises(SystemExit) as failure:
        probe.main()
    assert failure.value.code == 2
    assert (tmp_path / "probe.lock").read_text() == "synthetic-owner"


def test_static_member_size_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import gtfs_probe

    archive = tmp_path / "large.zip"
    with ZipFile(archive, "w") as z:
        z.writestr("trips.txt", "trip_id\n" + "x" * 100)
    monkeypatch.setattr(gtfs_probe, "MAX_MEMBER_BYTES", 10)
    with pytest.raises(ValueError, match="Static member"):
        Schedule.read(archive)


def test_entity_fingerprint_ignores_header_and_order_but_not_content() -> None:
    feed = sample()
    original = entity_fingerprint(feed)
    feed.header.timestamp += 30
    assert entity_fingerprint(feed) == original
    second = feed.entity.add(id="other")
    second.alert.header_text.translation.add(text="synthetic alert")
    ordered = entity_fingerprint(feed)
    feed.entity.reverse()
    assert entity_fingerprint(feed) == ordered
    feed.entity.reverse()
    feed.entity[0].vehicle.position.longitude += 0.1
    assert entity_fingerprint(feed) != original


@pytest.mark.parametrize("relationship", [pb.TripDescriptor.ADDED, pb.TripDescriptor.CANCELED])
def test_non_scheduled_trip_classified_before_static_lookup(
    schedule: Schedule, relationship: int
) -> None:
    trip = sample().entity[0].vehicle.trip
    trip.trip_id = "not-in-static"
    trip.schedule_relationship = relationship
    assert schedule.linkage(trip) == "non_scheduled"
    trip.ClearField("trip_id")
    assert schedule.linkage(trip) == "non_scheduled"


def retained_run(tmp_path: Path, schedule: Schedule) -> dict:
    clock = Clock()
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, stream=httpx.ByteStream(sample().SerializeToString()))
        )
    ) as client:
        return probe.run_probe(
            client,
            schedule,
            "secret",
            "KeyID",
            tmp_path,
            60,
            sleep=clock.sleep,
            monotonic=clock.read,
        )


def test_replay_matches_live_analysis_without_network_or_env(
    tmp_path: Path, schedule: Schedule, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys

    expected = retained_run(tmp_path, schedule)
    original = (tmp_path / "report.json").read_bytes()

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Replay must not access network or credentials")

    monkeypatch.setattr(httpx, "Client", forbidden)
    monkeypatch.setattr(probe, "ProbeSettings", forbidden)
    monkeypatch.setattr(
        sys,
        "argv",
        ["probe", "--static-zip", str(tmp_path / "tram.zip"), "--replay", str(tmp_path)],
    )
    assert probe.main() == 0
    actual = json.loads((tmp_path / "replay.json").read_text())
    assert actual["captures"] == expected["captures"]
    assert actual["capture_code"] == expected["capture_code"]
    assert (tmp_path / "report.json").read_bytes() == original


def test_replay_legacy_recomputes_entity_and_motion(tmp_path: Path, schedule: Schedule) -> None:
    expected = retained_run(tmp_path, schedule)
    legacy = json.loads(json.dumps(expected))
    legacy.pop("capture_code")
    for row in legacy["captures"]:
        for name in (
            "summary",
            "entity_payload_sha256",
            "unchanged_entities",
            "position_comparison",
        ):
            row.pop(name, None)
    (tmp_path / "report.json").write_text(json.dumps(legacy))
    actual = probe.replay_report(tmp_path, schedule)
    assert actual["captures"] == expected["captures"]
    assert actual["capture_code"] is None
    assert actual["captures"][3]["unchanged_entities"] is True
    assert actual["captures"][3]["position_comparison"]["coordinates_changed"] == 0


@pytest.mark.parametrize("tamper", ["payload", "static", "path", "missing", "naive_time"])
def test_replay_rejects_tampered_or_incomplete_evidence(
    tmp_path: Path, schedule: Schedule, tamper: str
) -> None:
    report = retained_run(tmp_path, schedule)
    first = tmp_path / report["captures"][0]["payload"]
    if tamper == "payload":
        first.write_bytes(b"changed")
    elif tamper == "static":
        report["static"]["sha256"] = "wrong"
    elif tamper == "path":
        report["captures"][0]["payload"] = "../outside.pb"
    elif tamper == "missing":
        first.unlink()
    else:
        report["captures"][0]["received_at"] = "2026-10-07T03:44:15"
    (tmp_path / "report.json").write_text(json.dumps(report))
    with pytest.raises((ValueError, FileNotFoundError)):
        probe.replay_report(tmp_path, schedule)


def test_settings_use_shared_file_configuration_and_environment_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = tmp_path / ".env"
    env.write_text("DTP_OPENDATA_API_KEY=from-file\nOTHER_SETTING=ignored\n")
    monkeypatch.delenv("DTP_OPENDATA_API_KEY", raising=False)
    settings = probe.ProbeSettings(_env_file=env)
    assert settings.dtp_opendata_api_key.get_secret_value() == "from-file"
    assert "from-file" not in repr(settings)
    monkeypatch.setenv("DTP_OPENDATA_API_KEY", "from-environment")
    assert (
        probe.ProbeSettings(_env_file=env).dtp_opendata_api_key.get_secret_value()
        == "from-environment"
    )

"""Raw-only telemetry uses fake HTTP and ephemeral test keys, never cloud credentials."""

import asyncio
import base64
import json
import sys
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from google.auth import crypt

from urbanpulse.adapters.capture_metrics import PREFIX, MonitoringTarget, Pulse, raw_series
from urbanpulse.adapters.capture_monitoring import TOKEN_URL, DeliveryError, MonitoringSink
from urbanpulse.adapters.capture_runtime import RuntimeObservation
from urbanpulse.contracts.capture_control import Summary
from urbanpulse.contracts.local_capture import FEEDS

NOW = datetime(2026, 1, 1, tzinfo=UTC)
TARGET = MonitoringTarget(project="example-capture", collector="pilot")


def pulse(at=NOW, **changes):
    return {
        "kind": "collector_heartbeat_dry_run",
        "mode": "live",
        "state": "running",
        "emitted_at": at.isoformat(),
        "last_capture_at": {},
        "free_bytes": 10**9,
        "free_inodes": 10000,
        "session_id": "never-a-label",
    } | changes


def values(series):
    return {
        (item["metric"]["type"].removeprefix(PREFIX), item["metric"]["labels"].get("feed")): int(
            item["points"][0]["value"]["int64Value"]
        )
        for item in series
    }


@pytest.fixture(scope="module")
def key_material():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    content = {
        "type": "service_account",
        "project_id": TARGET.project,
        "client_email": "collector@" + TARGET.project + ".iam.gserviceaccount.com",
        "private_key_id": "a" * 40,
        "private_key": private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode(),
        "token_uri": TOKEN_URL,
    }
    public = (
        private.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    return content, public


@pytest.fixture
def boundary(tmp_path, key_material):
    key = tmp_path / "test-only.json"
    key.write_text(json.dumps(key_material[0]), encoding="utf-8")
    return SimpleNamespace(
        key=key,
        public=key_material[1],
        now=NOW,
        mono=100.0,
        calls=[],
        logs=[],
        status=200,
        response={},
        auth_status=200,
    )


def sink_for(boundary, handler=None, **options):
    def default(request):
        boundary.calls.append(request)
        if str(request.url) == TOKEN_URL:
            return httpx.Response(
                boundary.auth_status,
                json={
                    "access_token": "test-only-access-token",
                    "expires_in": 3600,
                    "token_type": "Bearer",
                },
            )
        return httpx.Response(boundary.status, json=boundary.response)

    return MonitoringSink(
        TARGET,
        boundary.key,
        wall_clock=lambda: boundary.now,
        monotonic=lambda: boundary.mono,
        report=boundary.logs.append,
        transport=httpx.MockTransport(handler or default),
        **options,
    )


def advance(boundary, seconds=30):
    boundary.now += timedelta(seconds=seconds)
    boundary.mono += seconds


def test_unknown_has_no_age_no_upload_and_only_fixed_labels():
    series = raw_series(Pulse.model_validate(pulse()), TARGET)
    metrics = values(series)
    assert len(series) == 6 and metrics[("heartbeat", None)] == 1
    assert all(metrics[("capture_success_known", feed)] == 0 for feed in FEEDS)
    assert not any("age" in name or "upload" in name for name, _ in metrics)
    assert "session" not in json.dumps(series)
    for item in series:
        assert item["resource"] == {
            "type": "generic_task",
            "labels": {
                "project_id": TARGET.project,
                "location": "australia-southeast2",
                "namespace": "urbanpulse",
                "job": "capture",
                "task_id": TARGET.collector,
            },
        }


def test_restart_uses_durable_success_and_capacity_not_session_outcomes(tmp_path):
    summary = Summary(
        last_capture_at={
            "live/vehicle-positions": NOW - timedelta(seconds=95),
            "fixture/trip-updates": NOW,
        }
    )
    records = []
    monitor = RuntimeObservation(
        tmp_path, "live", lambda: summary, read_capacity=lambda _: (42, 17), send=records.append
    )
    monitor.pulse()
    current = json.loads(records[0])
    # Runtime clock is real; use that exact pulse to check a restart does not reset age.
    expected = int(
        (
            datetime.fromisoformat(current["emitted_at"]) - (NOW - timedelta(seconds=95))
        ).total_seconds()
    )
    metrics = values(raw_series(Pulse.model_validate(current), TARGET))
    assert metrics[("capture_age_seconds", "vehicle-positions")] == expected
    assert metrics[("capture_success_known", "trip-updates")] == 0
    assert metrics[("free_bytes", None)] == 42 and metrics[("free_inodes", None)] == 17


@pytest.mark.parametrize("state", ["stopped", "disk_reserve_reached", "inode_reserve_reached"])
def test_final_or_reserve_pulse_cannot_extend_heartbeat(state):
    metrics = values(raw_series(Pulse.model_validate(pulse(state=state)), TARGET))
    assert ("heartbeat", None) not in metrics
    assert ("free_bytes", None) in metrics


def test_signed_scoped_auth_then_expected_monitoring_request(boundary):
    sink = sink_for(boundary)
    sink(json.dumps(pulse()))
    auth, write = boundary.calls
    form = parse_qs(auth.content.decode())
    assert form["grant_type"] == ["urn:ietf:params:oauth:grant-type:jwt-bearer"]
    # Verify signature without using the real system clock for deterministic expiry.
    assertion = form["assertion"][0]
    encoded_header, encoded_claims, encoded_signature = assertion.split(".")

    def decode(part):
        return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))

    header, claims = json.loads(decode(encoded_header)), json.loads(decode(encoded_claims))
    signed = (encoded_header + "." + encoded_claims).encode()
    signature = decode(encoded_signature)

    assert crypt.RSAVerifier.from_string(boundary.public).verify(signed, signature)
    assert header["alg"] == "RS256"
    assert claims == {
        "iss": "collector@" + TARGET.project + ".iam.gserviceaccount.com",
        "scope": "https://www.googleapis.com/auth/monitoring.write",
        "aud": TOKEN_URL,
        "iat": int(NOW.timestamp()),
        "exp": int(NOW.timestamp()) + 600,
    }
    assert (
        str(write.url) == "https://monitoring.googleapis.com/v3/projects/example-capture/timeSeries"
    )
    assert write.headers["authorization"] == "Bearer test-only-access-token"
    assert len(json.loads(write.content)["timeSeries"]) == 6
    assert json.loads(boundary.logs[-1])["status"] == "sent"
    assert "test-only-access-token" not in "".join(boundary.logs)


def test_token_reused_refreshed_and_401_discards_without_immediate_retry(boundary):
    sink = sink_for(boundary)
    sink(json.dumps(pulse()))
    advance(boundary)
    sink(json.dumps(pulse(boundary.now)))
    assert len(boundary.calls) == 3
    boundary.status = 401
    advance(boundary)
    with pytest.raises(DeliveryError, match="unconfirmed"):
        sink(json.dumps(pulse(boundary.now)))
    assert len(boundary.calls) == 4
    boundary.status = 200
    advance(boundary)
    sink(json.dumps(pulse(boundary.now)))
    assert len(boundary.calls) == 6
    advance(boundary, 3541)
    sink(json.dumps(pulse(boundary.now)))
    assert len(boundary.calls) == 8


@pytest.mark.parametrize("status", [400, 403, 429, 500])
def test_partial_or_rejected_batch_is_unconfirmed_redacted_and_not_replayed(boundary, status):
    boundary.status = status
    boundary.response = {
        "error": {
            "message": "private-provider-message test-only-access-token",
            "details": [{"totalPointCount": 6, "successPointCount": 4}],
        }
    }
    sink = sink_for(boundary)
    with pytest.raises(DeliveryError, match="write_unconfirmed"):
        sink(json.dumps(pulse()))
    assert len(boundary.calls) == 2
    report = json.loads(boundary.logs[-1])
    assert len(report["unconfirmed"]) == 6
    assert "private-provider" not in "".join(boundary.logs)
    with pytest.raises(DeliveryError):
        sink(json.dumps(pulse()))
    assert len(boundary.calls) == 2
    boundary.status, boundary.response = 200, {}
    advance(boundary)
    sink(json.dumps(pulse(boundary.now)))
    assert len(boundary.calls) == 3


@pytest.mark.parametrize(
    "change",
    [
        {"mode": "fixture"},
        {"last_capture_at": {"fixture/vehicle-positions": NOW.isoformat()}},
        {"last_capture_at": {"live/vehicle-positions": (NOW + timedelta(seconds=1)).isoformat()}},
        {"emitted_at": (NOW - timedelta(seconds=6)).isoformat()},
        {"emitted_at": (NOW + timedelta(seconds=1)).isoformat()},
        {"free_bytes": -1},
        {"free_inodes": True},
    ],
)
def test_invalid_truth_or_clock_never_touches_network(boundary, change):
    sink = sink_for(boundary)
    with pytest.raises(DeliveryError):
        sink(json.dumps(pulse(**change)))
    assert not boundary.calls


def test_backward_wall_clock_is_refused_even_if_monotonic_advances(boundary):
    sink = sink_for(boundary)
    sink(json.dumps(pulse()))
    boundary.mono += 30
    boundary.now -= timedelta(seconds=30)
    with pytest.raises(DeliveryError):
        sink(json.dumps(pulse(boundary.now)))
    assert len(boundary.calls) == 2


def test_forced_pulses_do_not_exceed_provider_minimum_spacing(boundary):
    sink = sink_for(boundary)
    sink(json.dumps(pulse()))
    advance(boundary, 1)
    sink(json.dumps(pulse(boundary.now, state="stopped")))
    assert len(boundary.calls) == 2
    advance(boundary, 29)
    sink(json.dumps(pulse(boundary.now)))
    assert len(boundary.calls) == 3


@pytest.mark.parametrize("kind", ["identity", "oversize", "token-uri", "missing"])
def test_bad_key_is_redacted_before_any_network(boundary, kind):
    doc = json.loads(boundary.key.read_text())
    if kind == "missing":
        boundary.key.unlink()
    else:
        doc[{"identity": "project_id", "oversize": "extra", "token-uri": "token_uri"}[kind]] = (
            "x" * 20000 if kind == "oversize" else "untrusted"
        )
        boundary.key.write_text(json.dumps(doc))
    sink = sink_for(boundary)
    with pytest.raises(DeliveryError) as error:
        sink(json.dumps(pulse()))
    assert not boundary.calls
    assert str(boundary.key) not in str(error.value)
    assert "private_key" not in "".join(boundary.logs)


def test_authentication_failure_is_not_a_success_or_monitoring_call(boundary):
    boundary.auth_status = 403
    with pytest.raises(DeliveryError, match="authentication_failed"):
        sink_for(boundary)(json.dumps(pulse()))
    assert len(boundary.calls) == 1


def test_redirect_is_never_followed(boundary):
    calls = []

    def redirect(request):
        calls.append(request)
        return httpx.Response(307, headers={"Location": "https://untrusted.example"}, json={})

    with pytest.raises(DeliveryError):
        sink_for(boundary, redirect)(json.dumps(pulse()))
    assert len(calls) == 1


@pytest.mark.parametrize("stage", ["auth", "write"])
def test_total_deadline_cancels_stalled_request_including_auth(boundary, stage):
    calls = []

    async def slow(request):
        calls.append(request)
        if stage == "write" and str(request.url) == TOKEN_URL:
            return httpx.Response(
                200, json={"access_token": "test-only", "expires_in": 3600, "token_type": "Bearer"}
            )
        await asyncio.sleep(10)
        raise AssertionError("request should have been cancelled")

    with pytest.raises(DeliveryError, match="deadline_exceeded"):
        sink_for(boundary, slow, budget_seconds=0.05)(json.dumps(pulse()))
    assert len(calls) == (1 if stage == "auth" else 2)


def test_slow_body_is_inside_same_total_deadline(boundary):
    class SlowBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"{"
            await asyncio.sleep(10)
            yield b"}"

    def handler(_):
        return httpx.Response(200, stream=SlowBody())

    with pytest.raises(DeliveryError, match="deadline_exceeded"):
        sink_for(boundary, handler, budget_seconds=0.05)(json.dumps(pulse()))


@pytest.mark.parametrize("body", [b"x" * 65537, b"not-json"], ids=["oversized", "invalid-json"])
def test_response_size_and_parsing_fail_closed(boundary, body):
    with pytest.raises(DeliveryError):
        sink_for(boundary, lambda _: httpx.Response(200, content=body))(json.dumps(pulse()))


def test_export_failure_does_not_interrupt_capture_and_logs_no_secrets(boundary, tmp_path):
    from itertools import repeat
    from threading import Event

    from test_local_collector import Clock, Journal, Source

    from urbanpulse.application.local_collector import collect

    clock, journal = Clock(), Journal()
    boundary.status = 403
    sink = sink_for(boundary)
    # Runtime emits actual clock timestamps; align the fake auth boundary with it.
    sink.wall_clock = lambda: datetime.now(UTC)
    monitor = RuntimeObservation(
        tmp_path,
        "live",
        Summary,
        read_capacity=lambda _: (10**9, 10000),
        send=sink,
        monotonic=clock.monotonic,
    )
    result = collect(
        journal,
        Source(clock, repeat(200)),
        mode="live",
        version="test",
        stop=Event(),
        max_attempts=2,
        max_seconds=120,
        interval=30,
        tick=monitor.pulse,
        before_capture=monitor.guard,
        after_capture=monitor.completed,
        monotonic=clock.monotonic,
        wait=clock.wait,
    )
    assert result.captured == 2 and monitor.send_failures >= 1
    assert "test-only-access-token" not in "".join(boundary.logs)


@pytest.mark.parametrize(
    "options",
    [
        ["--monitoring-project", "example-capture"],
        [
            "--monitoring-project",
            "example-capture",
            "--monitoring-collector",
            "pilot",
            "--monitoring-key-file",
            "test-only.json",
        ],
        [
            "--live",
            "--monitoring-project",
            "../other",
            "--monitoring-collector",
            "pilot",
            "--monitoring-key-file",
            "test-only.json",
        ],
    ],
)
def test_cli_refuses_invalid_or_fixture_export_before_store_mutation(
    tmp_path, monkeypatch, options
):
    from workers.capture.main import main

    store = tmp_path / "absent"
    monkeypatch.setattr(
        sys, "argv", ["capture", "serve", "--store", str(store), "--store-version", "v3", *options]
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2 and not store.exists()


def test_short_wall_interval_after_clock_adjustment_is_not_published(boundary):
    sink = sink_for(boundary)
    sink(json.dumps(pulse()))
    boundary.mono += 30
    boundary.now += timedelta(milliseconds=1)
    sink(json.dumps(pulse(boundary.now)))
    assert len(boundary.calls) == 2


def test_linux_live_cli_wires_sink_without_changing_durable_captures(
    boundary, tmp_path, monkeypatch
):
    if sys.platform != "linux":
        pytest.skip("Linux durable-store integration")

    from test_local_collector import Clock

    from urbanpulse.adapters import capture_journal as storage
    from urbanpulse.adapters.capture_v3 import V3Journal
    from urbanpulse.adapters.synthetic_capture import SyntheticCapture
    from workers.capture import main as worker

    store = tmp_path / "store"
    store.mkdir()
    monkeypatch.setattr(storage, "local_filesystem", lambda _: "test-filesystem")
    with V3Journal(store).locked(initialize=True):
        pass
    clock = Clock()
    real_collect = worker.collect

    def finite_collect(*args, **kwargs):
        kwargs.update(
            continuous=False,
            max_attempts=2,
            initial_delay=0,
            monotonic=clock.monotonic,
            wait=clock.wait,
        )
        return real_collect(*args, **kwargs)

    sink = sink_for(boundary)
    sink.wall_clock = lambda: datetime.now(UTC)
    sink.monotonic = clock.monotonic
    configured = []

    def exporter(target, key_file):
        configured.append((target, key_file))
        return sink

    monkeypatch.setattr(worker, "MonitoringSink", exporter)
    monkeypatch.setattr(worker, "collect", finite_collect)
    monkeypatch.setattr(worker, "TransportCapture", lambda *_: SyntheticCapture())
    monkeypatch.setattr(worker.signal, "signal", lambda *_: None)
    dtp = tmp_path / "test-only-dtp"
    dtp.write_text("test-only")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "capture",
            "serve",
            "--live",
            "--store",
            str(store),
            "--store-version",
            "v3",
            "--key-file",
            str(dtp),
            "--monitoring-project",
            TARGET.project,
            "--monitoring-collector",
            TARGET.collector,
            "--monitoring-key-file",
            str(boundary.key),
        ],
    )
    assert worker.main() == 0
    assert configured == [(TARGET, boundary.key)]
    assert len(boundary.calls) >= 2
    with V3Journal(store).locked() as journal:
        journal.recover()
        assert len(journal.control.summary.last_capture_at) == 2
    assert json.loads(boundary.logs[0])["status"] == "sent"


def test_stalled_delivery_cleanup_never_blocks_collector_or_queues_attempts(boundary):
    from threading import Event

    release = Event()
    started = []
    sink = sink_for(boundary, budget_seconds=0.05)

    async def slow_cleanup(_):
        started.append(True)
        # Model OS resolver cleanup outside asyncio's cancellable I/O.
        release.wait(3)

    sink.deliver = slow_cleanup
    try:
        with pytest.raises(DeliveryError, match="deadline_exceeded"):
            sink(json.dumps(pulse()))
        advance(boundary)
        with pytest.raises(DeliveryError, match="previous_delivery_pending"):
            sink(json.dumps(pulse(boundary.now)))
        assert started == [True]
    finally:
        release.set()
        assert sink.pending.wait(3)

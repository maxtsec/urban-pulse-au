"""HTTP-boundary tests use synthetic bytes and never contact the provider."""

from datetime import UTC, datetime

import httpx
import pytest
from pydantic import SecretStr

from urbanpulse.adapters import transport_capture as transport


def test_exact_bytes_and_header_are_preserved() -> None:
    payload = b"\x00synthetic\xff"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["KeyID"] == "test-secret"
        assert request.headers["accept-encoding"] == "identity"
        assert not request.url.query
        assert request.url.host == "api.opendata.transport.vic.gov.au"
        return httpx.Response(200, stream=httpx.ByteStream(payload))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = transport.TransportCapture(client, SecretStr("test-secret")).fetch(
            "vehicle-positions"
        )
    assert result.payload == payload and result.reason is None
    assert result.requested_at <= result.received_at
    assert "synthetic" not in repr(result)


@pytest.mark.parametrize("status", [301, 302, 401, 403, 429, 500, 503])
def test_failures_do_not_retry_redirect_or_expose_body(status: int) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            status,
            headers={"location": "https://elsewhere.example", "retry-after": "120"},
            content=b"secret-echo",
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = transport.TransportCapture(client, SecretStr("test-secret")).fetch("trip-updates")
    assert len(calls) == 1
    assert result.payload is None and result.reason == "http_error"
    assert result.http_status == status and result.retry_after_seconds == 120
    assert "secret-echo" not in repr(result)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("-1", None),
        ("1.5", None),
        ("10", 10),
        ("garbage", None),
        ("Wed, 07 Oct 2026 12:01:00 GMT", 60),
        ("Wed, 07 Oct 2026 11:59:00 GMT", 0),
    ],
)
def test_retry_after(value: str | None, expected: float | None) -> None:
    assert transport.retry_after(value, datetime(2026, 10, 7, 12, tzinfo=UTC)) == expected


def test_size_and_encoding_fail_without_partial_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transport, "MAX_BYTES", 3)
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, stream=httpx.ByteStream(b"1234"))
        )
    ) as client:
        result = transport.TransportCapture(client, SecretStr("key")).fetch("service-alerts")
    assert result.reason == "size_limit" and result.payload is None
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, headers={"Content-Encoding": "gzip"}, stream=httpx.ByteStream(b"123")
            )
        )
    ) as client:
        result = transport.TransportCapture(client, SecretStr("key")).fetch("service-alerts")
    assert result.reason == "encoding" and result.payload is None


def test_network_error_is_redacted() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("secret-echo", request=request)

    with httpx.Client(transport=httpx.MockTransport(fail)) as client:
        result = transport.TransportCapture(client, SecretStr("key")).fetch("vehicle-positions")
    assert result.reason == "network_error" and result.payload is None
    assert "secret-echo" not in repr(result)

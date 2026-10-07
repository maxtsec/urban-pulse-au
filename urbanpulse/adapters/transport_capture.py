"""Bounded raw Transport Victoria fetches, independent of capture persistence."""

import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx
from pydantic import SecretStr

from urbanpulse.contracts.local_capture import FEEDS, MAX_BYTES, FetchResult, TramFeed

BASE = "https://api.opendata.transport.vic.gov.au/opendata/public-transport/gtfs/realtime/v1/tram"


def retry_after(value: str | None, received_at: datetime) -> float | None:
    """Honor either RFC delay seconds or a dated Retry-After; absence stays explicit."""
    if value is None:
        return None
    value = value.strip()
    if value.isascii() and value.isdecimal():
        try:
            delay = int(value)
            return float(delay) if delay <= 2**31 else None
        except ValueError:
            return None
    try:
        timestamp = parsedate_to_datetime(value)
        if timestamp.tzinfo is None:
            return None
        return max(0.0, (timestamp - received_at).total_seconds())
    except (ValueError, TypeError, OverflowError):
        return None


class TransportCapture:
    def __init__(self, client: httpx.Client, key: SecretStr) -> None:
        self.client = client
        self.key = key

    def fetch(self, feed: TramFeed) -> FetchResult:
        if feed not in FEEDS:
            raise ValueError("Unsupported tram feed")
        requested_at = datetime.now(UTC)
        started = time.monotonic()
        status: int | None = None
        try:
            with self.client.stream(
                "GET",
                BASE + "/" + feed,
                headers={"KeyID": self.key.get_secret_value(), "Accept-Encoding": "identity"},
                follow_redirects=False,
                timeout=10,
            ) as response:
                status = response.status_code
                if status != 200:
                    received_at = datetime.now(UTC)
                    return FetchResult(
                        requested_at,
                        received_at,
                        status,
                        None,
                        "http_error",
                        retry_after(response.headers.get("retry-after"), received_at),
                    )
                if response.headers.get("content-encoding", "identity").lower() != "identity":
                    return FetchResult(requested_at, datetime.now(UTC), status, None, "encoding")
                body = bytearray()
                for chunk in response.iter_raw():
                    if len(body) + len(chunk) > MAX_BYTES:
                        return FetchResult(
                            requested_at, datetime.now(UTC), status, None, "size_limit"
                        )
                    if time.monotonic() - started > 15:
                        return FetchResult(
                            requested_at, datetime.now(UTC), status, None, "time_limit"
                        )
                    body.extend(chunk)
            content_type = response.headers.get("content-type", "").split(";")[0].lower()
            # Store only known media types, never arbitrary upstream header text.
            content_type = (
                content_type
                if content_type
                in {"application/octet-stream", "application/x-protobuf", "application/protobuf"}
                else None
            )
            return FetchResult(
                requested_at, datetime.now(UTC), status, bytes(body), content_type=content_type
            )
        except httpx.HTTPError:
            # No upstream error body, exception text or credential-bearing headers escape.
            return FetchResult(requested_at, datetime.now(UTC), status, None, "network_error")

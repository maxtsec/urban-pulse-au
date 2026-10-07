"""Small, clearly synthetic raw fixture; no socket or credential access."""

from datetime import UTC, datetime

from urbanpulse.contracts.local_capture import FetchResult, TramFeed


class SyntheticCapture:
    def fetch(self, feed: TramFeed) -> FetchResult:
        requested = datetime.now(UTC)
        return FetchResult(
            requested,
            datetime.now(UTC),
            200,
            ("synthetic-capture-v1:" + feed).encode() + b"\x00\xff",
            content_type="application/octet-stream",
        )

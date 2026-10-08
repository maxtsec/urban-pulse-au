"""Single-attempt OAuth and Monitoring delivery; bounded async I/O behind a sync sink."""

import asyncio
import json
import stat
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Thread
from typing import Literal

import httpx
from google.auth import crypt, jwt
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from urbanpulse.adapters.capture_metrics import (
    MonitoringTarget,
    Pulse,
    current_pulse,
    raw_series,
)

TOKEN_URL = "https://oauth2.googleapis.com/token"
MAX_RESPONSE = 65536


class DeliveryError(RuntimeError):
    """Only fixed codes, never provider response bodies or credential details."""


class ServiceKey(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["service_account"]
    project_id: str
    client_email: str
    private_key_id: str = Field(pattern=r"^[a-f0-9]{40}$")
    private_key: SecretStr
    token_uri: Literal["https://oauth2.googleapis.com/token"]


class MonitoringSink:
    def __init__(
        self,
        target: MonitoringTarget,
        key_file: Path,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        wall_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        monotonic: Callable[[], float] = time.monotonic,
        report: Callable[[str], None] = lambda line: print(line, flush=True),
        budget_seconds: float = 5,
    ) -> None:
        if not 0 < budget_seconds <= 5:
            raise ValueError("monitoring_budget_invalid")
        self.target, self.key_file = target, key_file
        self.transport, self.wall_clock, self.monotonic = transport, wall_clock, monotonic
        self.report, self.budget_seconds = report, budget_seconds
        self.previous: datetime | None = None
        self.last_attempt = float("-inf")
        self.token = SecretStr("")
        self.token_until = 0.0
        self.pending: Event | None = None

    def __call__(self, line: str) -> None:
        series: list[dict[str, object]] = []
        try:
            if len(line) > MAX_RESPONSE:
                raise DeliveryError("pulse_too_large")
            pulse = Pulse.model_validate_json(line)
            current_pulse(pulse, self.wall_clock(), self.previous)
            series = raw_series(pulse, self.target)
            # Forced final pulses can occur immediately after a normal pulse.
            # Do not replay any potentially partially accepted batch.
            if self.monotonic() - self.last_attempt < 5 or (
                self.previous is not None and (pulse.emitted_at - self.previous).total_seconds() < 5
            ):
                return
            self.previous = pulse.emitted_at
            self.last_attempt = self.monotonic()
            self.attempt(series)
            self.report(
                json.dumps(
                    {"kind": "collector_monitoring", "status": "sent", "series": len(series)}
                )
            )
        except Exception as error:
            code = str(error) if isinstance(error, DeliveryError) else "export_failed"
            try:
                self.report(
                    json.dumps(
                        {
                            "kind": "collector_monitoring",
                            "status": code,
                            "unconfirmed": [item["metric"] for item in series],
                        }
                    )
                )
            except Exception:
                pass
            raise DeliveryError(code) from None

    def attempt(self, series: list[dict[str, object]]) -> None:
        # asyncio cancellation cannot interrupt an OS DNS lookup, and asyncio.run
        # waits for its resolver executor during shutdown. Keep that cleanup off
        # the collection thread. At most one attempt exists; never queue pulses.
        if self.pending is not None and not self.pending.is_set():
            raise DeliveryError("previous_delivery_pending")
        done = Event()
        errors: list[Exception] = []
        self.pending = done

        def execute() -> None:
            try:
                asyncio.run(self.deliver(series))
            except Exception as error:
                errors.append(error)
            finally:
                done.set()

        Thread(target=execute, name="collector-monitoring", daemon=True).start()
        if not done.wait(self.budget_seconds):
            raise DeliveryError("deadline_exceeded")
        if errors:
            raise errors[0]

    async def post(
        self, client: httpx.AsyncClient, url: str, **kwargs: object
    ) -> tuple[int, object]:
        # All callers are inside one asyncio deadline, including DNS, headers,
        # trickled bodies, auth and publication. No SDK retries or redirects.
        async with client.stream("POST", url, **kwargs) as response:  # type: ignore[arg-type]
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > MAX_RESPONSE:
                    raise DeliveryError("response_too_large")
            try:
                document: object = json.loads(body)
            except (ValueError, UnicodeError):
                raise DeliveryError("invalid_response") from None
            return response.status_code, document

    async def access_token(self, client: httpx.AsyncClient) -> str:
        if self.token.get_secret_value() and self.monotonic() < self.token_until:
            return self.token.get_secret_value()
        # Reload only when refreshing, permitting operator-managed key rotation.
        metadata = self.key_file.lstat()
        if not stat.S_ISREG(metadata.st_mode) or not 0 < metadata.st_size <= 16384:
            raise DeliveryError("credential_file_invalid")
        with self.key_file.open("rb") as stream:
            content = stream.read(16385)
        if len(content) > 16384:
            raise DeliveryError("credential_file_invalid")
        key = ServiceKey.model_validate_json(content)
        if key.project_id != self.target.project or key.client_email != self.target.service_account:
            raise DeliveryError("credential_identity_mismatch")
        signer = crypt.RSASigner.from_string(  # type: ignore[no-untyped-call]
            key.private_key.get_secret_value(), key.private_key_id
        )
        issued = int(self.wall_clock().timestamp())
        assertion = jwt.encode(  # type: ignore[no-untyped-call]
            signer,
            {
                "iss": key.client_email,
                "scope": "https://www.googleapis.com/auth/monitoring.write",
                "aud": TOKEN_URL,
                "iat": issued,
                "exp": issued + 600,
            },
        ).decode("ascii")
        status, value = await self.post(
            client,
            TOKEN_URL,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
        )
        if status != 200 or not isinstance(value, dict):
            raise DeliveryError("authentication_failed")
        token, expires = value.get("access_token"), value.get("expires_in")
        if (
            not isinstance(token, str)
            or not token
            or len(token) > 8192
            or type(expires) is not int
            or not 60 < expires <= 3600
            or value.get("token_type", "").lower() != "bearer"
        ):
            raise DeliveryError("authentication_failed")
        self.token = SecretStr(token)
        self.token_until = self.monotonic() + expires - 60
        return token

    async def deliver(self, series: list[dict[str, object]]) -> None:
        try:
            async with asyncio.timeout(self.budget_seconds):
                async with httpx.AsyncClient(
                    transport=self.transport,
                    trust_env=False,
                    follow_redirects=False,
                    timeout=self.budget_seconds,
                ) as client:
                    token = await self.access_token(client)
                    status, document = await self.post(
                        client,
                        f"https://monitoring.googleapis.com/v3/projects/{self.target.project}/timeSeries",
                        headers={"Authorization": "Bearer " + token},
                        json={"timeSeries": series},
                    )
                    if status == 401:
                        self.token = SecretStr("")
                        self.token_until = 0
                    if status != 200:
                        # Partial writes arrive as error responses too. Conservatively
                        # treat the whole batch as unconfirmed; never resend its timestamp.
                        raise DeliveryError("write_unconfirmed")
                    if document != {}:
                        raise DeliveryError("unexpected_write_response")
        except TimeoutError:
            raise DeliveryError("deadline_exceeded") from None

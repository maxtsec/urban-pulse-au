"""Retain and verify a deterministic fixture bundle; no live collection."""

import hashlib
import json
from pathlib import Path
from typing import Any

from urbanpulse.application.city import CapturedCity
from urbanpulse.config import ROOT


def capture_city(destination: Path) -> str:
    payload = json.dumps(
        {
            "boundary": json.loads(
                (ROOT / "tests/fixtures/southbank.geojson").read_text(encoding="utf-8")
            ),
            "planning": json.loads(
                (ROOT / "tests/fixtures/planning-scenario.json").read_text(encoding="utf-8")
            ),
            "weather": json.loads(
                (ROOT / "tests/fixtures/weather-scenario.json").read_text(encoding="utf-8")
            ),
            "scenario": json.loads(
                (ROOT / "tests/fixtures/city-scenario.json").read_text(encoding="utf-8")
            ),
        },
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    digest = hashlib.sha256(payload).hexdigest()
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / f"{digest}.json"
    try:
        with path.open("xb") as stream:
            stream.write(payload)
    except FileExistsError:
        if path.read_bytes() != payload:
            raise ValueError("existing fixture capture does not match its identity") from None
    return digest


class LocalCityCapture:
    def __init__(self, destination: Path, capture_id: str) -> None:
        self.path = destination / f"{capture_id}.json"
        self.capture_id = capture_id

    def read(self) -> CapturedCity:
        payload = self.path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != self.capture_id:
            raise ValueError("fixture capture integrity check failed")
        data: dict[str, Any] = json.loads(payload)
        return CapturedCity(
            self.capture_id,
            data["boundary"],
            data["scenario"],
            data.get("weather"),
            data.get("planning"),
        )

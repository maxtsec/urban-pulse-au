"""Capture a synthetic fixture locally; live adapters are not yet implemented."""

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

from apps.api.main import ROOT


def capture(destination: Path) -> str:
    payload = (ROOT / "tests/fixtures/transport.json").read_bytes()
    capture_id = hashlib.sha256(payload).hexdigest()
    destination.mkdir(parents=True, exist_ok=True)
    (destination / f"{capture_id}.json").write_bytes(payload)
    print(json.dumps({"mode": "fixture", "capture_id": capture_id, "bytes": len(payload)}))
    return capture_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=30)
    args = parser.parse_args()
    if args.interval <= 0:
        parser.error("--interval must be positive")
    destination = ROOT / os.environ.get("RAW_STORAGE_PATH", ".local/raw")
    while True:
        capture(destination)
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()

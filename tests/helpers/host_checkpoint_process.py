"""Runtime-image host acceptance helper; never bypass filesystem validation."""

import hashlib
import json
import os
import sys
from pathlib import Path

from urbanpulse.adapters.capture_checkpoint import CheckpointJournal
from urbanpulse.adapters.capture_verify import CaptureVerifier
from urbanpulse.adapters.synthetic_capture import SyntheticCapture

root = Path("/data")
action = sys.argv[1]
point = sys.argv[2] if len(sys.argv) > 2 else ""


def crash(stage: str) -> None:
    if stage == point:
        os._exit(77)


if action == "verify":
    with CaptureVerifier(root, checkpoint=crash).locked() as journal:
        print(json.dumps(journal.verify(), sort_keys=True))
elif action == "capture":
    with CheckpointJournal(root, checkpoint=crash).locked() as journal:
        journal.recover()
        intent = journal.begin("fixture", "vehicle-positions", "host-acceptance")
        journal.complete(intent, SyntheticCapture().fetch("vehicle-positions"))
elif action in {"digest", "hashes"}:
    with CheckpointJournal(root).locked() as journal:
        hashes = {}
        for directory in ("captures", "by-sequence"):
            for path in sorted((root / directory).rglob("*")):
                if path.is_file():
                    hashes[str(path.relative_to(root))] = hashlib.sha256(
                        path.read_bytes()
                    ).hexdigest()
        sequences = []
        for sequence in (
            range(1, journal.control.next_capture_sequence) if action == "digest" else ()
        ):
            intent = journal.capture_at_sequence(sequence)
            if intent is None:
                raise RuntimeError("Expected finalized sequence")
            sequences.append(sequence)
        print(json.dumps({"hashes": hashes, "sequences": sequences}, sort_keys=True))
else:
    raise ValueError("Unknown host acceptance action")

if point:
    raise RuntimeError("Requested checkpoint was not reached")

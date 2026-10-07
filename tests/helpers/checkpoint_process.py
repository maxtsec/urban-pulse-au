"""Linux v2 crash driver; test storage injection is absent from runtime images."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from urbanpulse.adapters import capture_journal as storage
from urbanpulse.adapters.capture_checkpoint import CheckpointJournal
from urbanpulse.adapters.capture_verify import CaptureVerifier
from urbanpulse.adapters.synthetic_capture import SyntheticCapture

storage.local_filesystem = lambda _: "test-filesystem"
root, action, point = sys.argv[1:4]


def crash(stage: str) -> None:
    if stage == point:
        os._exit(77)


if action == "verify":
    with CaptureVerifier(Path(root), checkpoint=crash).locked() as journal:
        journal.verify()
else:
    with CheckpointJournal(Path(root), checkpoint=crash).locked(
        initialize=action == "init"
    ) as journal:
        journal.recover()
        if action == "capture":
            intent = journal.begin("fixture", "vehicle-positions", "test")
            journal.complete(intent, SyntheticCapture().fetch("vehicle-positions"))

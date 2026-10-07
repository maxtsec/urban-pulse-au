"""Linux v3 crash driver; test-only filesystem injection and synthetic records."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from v3_records import deliver

from urbanpulse.adapters import capture_journal as storage
from urbanpulse.adapters.capture_v3 import V3Journal
from urbanpulse.adapters.capture_v3_verify import V3Verifier
from urbanpulse.adapters.synthetic_capture import SyntheticCapture

storage.local_filesystem = lambda _: "test-filesystem"
root, action, point = sys.argv[1:4]


def crash(stage):
    if stage == point:
        os._exit(77)


if action == "verify":
    with V3Verifier(Path(root), checkpoint=crash).locked() as journal:
        journal.verify()
else:
    with V3Journal(Path(root), checkpoint=crash).locked(initialize=action == "init") as journal:
        journal.recover()
        if action == "capture":
            intent = journal.begin("fixture", "vehicle-positions", "synthetic-v3")
            journal.complete(intent, SyntheticCapture().fetch("vehicle-positions"))
        elif action == "delivery":
            deliver(journal)

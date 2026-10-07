"""Child process intentionally dies at journal publication checkpoints."""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from urbanpulse.adapters.capture_journal import CaptureJournal
from urbanpulse.adapters.synthetic_capture import SyntheticCapture

root = Path(sys.argv[1])
point = sys.argv[2]


def crash(stage: str) -> None:
    if stage == point:
        os._exit(77)


with CaptureJournal(root, checkpoint=crash).locked() as journal:
    journal.recover()
    if point == "hold":
        print("locked", flush=True)
        time.sleep(60)
    else:
        intent = journal.begin("fixture", "vehicle-positions", "test")
        journal.complete(intent, SyntheticCapture().fetch("vehicle-positions"))

"""Test-only producer/checkpoint transaction pause points."""

import sys
import threading

from urbanpulse.adapters.city_runs import PostgresCityRuns
from urbanpulse.adapters.city_store import CityInputStore, engine_for
from urbanpulse.adapters.event_recovery import PostgresRecoveryStore
from urbanpulse.adapters.postgis import PostgisMembership
from urbanpulse.config import Settings

stage = sys.argv[1]


def pause():
    print(stage, flush=True)
    threading.Event().wait(60)
    raise RuntimeError("parent failed to terminate the test process")


class PausedRuns(PostgresCityRuns):
    def activate(self, transaction, run):
        result = super().activate(transaction, run)
        if stage == "producer-staged" or stage == "checkpoint-written" and run["completed"] >= 0:
            pause()
        return result


url = Settings().database_url
engine = engine_for(url)
try:
    city = PausedRuns(PostgresRecoveryStore(engine), CityInputStore(engine), PostgisMembership(url))
    if stage == "producer-staged":
        city.advance("crash", 0)
    else:
        city.progress()
        if stage == "checkpoint-committed":
            pause()
finally:
    engine.dispose()

"""Test-only process pause seams; the operator CLI exposes no crash controls."""

import sys
import threading

from urbanpulse.adapters.city_store import engine_for
from urbanpulse.adapters.event_recovery import PostgresRecoveryStore
from urbanpulse.adapters.recovery_probe import CONSUMER, apply_probe
from urbanpulse.application.event_worker import EventWorker
from urbanpulse.config import Settings

stage = sys.argv[1]


def pause(name):
    if stage == name:
        print(name, flush=True)
        threading.Event().wait(60)
        raise RuntimeError("parent failed to terminate the child")


class PausedStore(PostgresRecoveryStore):
    def complete(self, claim, effect):
        pause("claimed")
        result = super().complete(claim, effect)
        pause("committed")
        return result


def handler(claim, transaction, wire):
    apply_probe(claim, transaction, wire)
    pause("effect-written")


engine = engine_for(Settings().database_url)
try:
    EventWorker(PausedStore(engine), CONSUMER, handler).step()
finally:
    engine.dispose()

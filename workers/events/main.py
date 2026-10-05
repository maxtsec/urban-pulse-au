"""Local durable recovery probe and operator commands (no HTTP replay endpoint)."""

import argparse
import math
import signal
import threading

from sqlalchemy.exc import SQLAlchemyError

from urbanpulse.adapters.city_store import engine_for
from urbanpulse.adapters.event_recovery import PostgresRecoveryStore
from urbanpulse.adapters.recovery_probe import CONSUMER, apply_probe
from urbanpulse.application.durable_delivery import ReplayReason, StaleClaim, StorageUnavailable
from urbanpulse.application.event_worker import EventWorker
from urbanpulse.config import ROOT, Settings
from workers.runtime import emit, poll


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    seed = commands.add_parser("seed-probe")
    seed.add_argument("--context", required=True)
    run = commands.add_parser("run")
    run.add_argument("--once", action="store_true")
    run.add_argument("--poll-seconds", type=float, default=0.5)
    run.add_argument("--lease-seconds", type=float, default=30)
    listing = commands.add_parser("list")
    listing.add_argument("--context", required=True)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("delivery_id")
    replay = commands.add_parser("replay")
    replay.add_argument("delivery_id")
    replay.add_argument("--generation", type=int, required=True)
    replay.add_argument("--reason", choices=[item.value for item in ReplayReason], required=True)
    commands.add_parser("metrics")
    args = parser.parse_args()
    if args.command == "run" and (
        not math.isfinite(args.poll_seconds)
        or not 0 < args.poll_seconds <= 60
        or not math.isfinite(args.lease_seconds)
        or not 0 < args.lease_seconds <= 3600
    ):
        parser.error("poll interval must be in (0, 60] and lease in (0, 3600]")
    engine = None
    try:
        engine = engine_for(Settings().database_url)
        store = PostgresRecoveryStore(engine)
        if args.command == "seed-probe":
            wire = (ROOT / "tests/fixtures/vehicle-position-event.json").read_text(encoding="utf-8")
            with store.transaction() as transaction:
                publication = transaction.publish(args.context, wire, (CONSUMER,))
            emit({"mode": "synthetic-recovery-probe", "publication_id": publication})
        elif args.command == "list":
            emit(store.list_deliveries(args.context))
        elif args.command == "inspect":
            emit(store.inspect(args.delivery_id))
        elif args.command == "replay":
            emit(
                {
                    "generation": store.replay(
                        args.delivery_id, args.generation, ReplayReason(args.reason)
                    )
                }
            )
        elif args.command == "metrics":
            emit(store.metrics(CONSUMER))
        else:
            stop = threading.Event()

            def stopping(signum: int, frame: object) -> None:
                stop.set()

            signal.signal(signal.SIGINT, stopping)
            signal.signal(signal.SIGTERM, stopping)
            worker = EventWorker(store, CONSUMER, apply_probe, lease_seconds=args.lease_seconds)
            poll(worker, stop, once=args.once, interval=args.poll_seconds)
        return 0
    except (SQLAlchemyError, StorageUnavailable):
        emit({"error": "database-unavailable-or-schema-invalid"})
        return 2
    except StaleClaim:
        emit({"error": "stale-generation-or-nonterminal-delivery"})
        return 3
    except (ValueError, LookupError):
        emit({"error": "invalid-request-or-unknown-delivery"})
        return 4
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())

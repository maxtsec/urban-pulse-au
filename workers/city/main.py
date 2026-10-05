"""Explicit durable fixture-run controls; browser requests remain read-only."""

import argparse
import signal
import threading

import psycopg
from sqlalchemy.exc import SQLAlchemyError

from urbanpulse.adapters.city_runs import PostgresCityRuns
from urbanpulse.adapters.city_store import CityInputStore, engine_for
from urbanpulse.adapters.event_recovery import PostgresRecoveryStore
from urbanpulse.adapters.postgis import PostgisMembership
from urbanpulse.application.city_checkpoints import CONSUMER, RESULT_CONSUMER, CityRunWorker
from urbanpulse.application.durable_delivery import StorageUnavailable
from urbanpulse.application.event_worker import EventWorker
from urbanpulse.application.scenarios import Scenario
from urbanpulse.config import Settings
from workers.runtime import emit, poll


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("run_id")
    create.add_argument("--scope")
    create.add_argument("--scenario", choices=list(Scenario), default="city")
    advance = commands.add_parser("advance")
    advance.add_argument("run_id")
    advance.add_argument("--seconds", type=int, required=True)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("run_id")
    inspect.add_argument("--seconds", type=int)
    run = commands.add_parser("run")
    run.add_argument("--once", action="store_true")
    commands.add_parser("metrics", help="read input/result consumer backlog and failure counts")
    args = parser.parse_args()
    engine = None
    try:
        url = Settings().database_url
        engine = engine_for(url)
        queue = PostgresRecoveryStore(engine)
        if args.command == "metrics":
            emit({"consumers": [queue.metrics(name) for name in (CONSUMER, RESULT_CONSUMER)]})
            return 0
        inputs = CityInputStore(engine)
        city = PostgresCityRuns(queue, inputs, PostgisMembership(url))
        if args.command == "create":
            city.create(args.run_id, args.scope or inputs.active_scope(), args.scenario)
            emit(city.inspect(args.run_id))
        elif args.command == "advance":
            city.advance(args.run_id, args.seconds)
            emit(city.inspect(args.run_id))
        elif args.command == "inspect":
            emit(city.inspect(args.run_id, args.seconds))
        else:
            stop = threading.Event()

            def stopping(signum: int, frame: object) -> None:
                stop.set()

            signal.signal(signal.SIGINT, stopping)
            signal.signal(signal.SIGTERM, stopping)
            worker = CityRunWorker(
                city,
                EventWorker(queue, CONSUMER, city.receive),
                EventWorker(queue, RESULT_CONSUMER, city.receive),
            )
            poll(worker, stop, once=args.once, interval=0.5)
        return 0
    except (StorageUnavailable, SQLAlchemyError, psycopg.Error):
        emit({"error": "database-unavailable-or-schema-invalid"})
        return 2
    except (ValueError, LookupError):
        emit({"error": "invalid-run-scope-or-clock"})
        return 4
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())

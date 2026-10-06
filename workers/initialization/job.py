"""Explicit, finite schema/fixture initialization using separate least-privilege logins."""

import argparse
import re
import signal
import tempfile
import threading
from dataclasses import dataclass
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any, cast

import psycopg
from alembic.script import ScriptDirectory

from urbanpulse.adapters.city_fixture import LocalCityCapture, capture_city
from urbanpulse.adapters.city_import import prepare_import
from urbanpulse.adapters.city_store import CityInputStore, migrate
from urbanpulse.adapters.demo_database import (
    EXPECTED_REVISION,
    configure_defaults,
    grant_access,
    require_database,
    role_names,
)
from urbanpulse.adapters.job_database import JobDatabase
from urbanpulse.adapters.postgis import PostgisMembership
from urbanpulse.config import ROOT, Settings
from workers.job_runtime import report, supervise
from workers.runtime import emit


@dataclass(frozen=True)
class InitializationRequest:
    operation: str
    database: str
    expected_revision: str
    role_prefix: str = "urbanpulse"
    expected_import_id: str | None = None
    timeout_seconds: int = 540

    def __post_init__(self) -> None:
        if self.operation not in ("migrate", "import"):
            raise ValueError("unknown initialization operation")
        if re.fullmatch(r"[a-z][a-z0-9_]{0,62}", self.database) is None:
            raise ValueError("invalid target database")
        role_names(self.role_prefix)
        if self.expected_revision != EXPECTED_REVISION:
            raise ValueError("revision must match the reviewed privilege matrix")
        if self.expected_import_id is not None and (
            self.operation != "import"
            or re.fullmatch(r"[0-9a-f]{64}", self.expected_import_id) is None
        ):
            raise ValueError("invalid expected import")
        if type(self.timeout_seconds) is not int or not 1 <= self.timeout_seconds <= 540:
            raise ValueError("timeout must be 1 to 540 seconds")


def execute(request: InitializationRequest) -> dict[str, str]:
    if ScriptDirectory(str(ROOT / "migrations")).get_current_head() != request.expected_revision:
        raise ValueError("image migration head differs from requested revision")
    url = Settings().database_url
    database = JobDatabase(url)
    try:
        # The explicit database/login and shared session lock are checked before any writes.
        with database.engine.begin() as connection:
            raw = cast(psycopg.Connection[Any], connection.connection.driver_connection)
            require_database(raw, request.database)
            wanted = role_names(request.role_prefix)[request.operation]
            if raw.execute("SELECT current_user").fetchone() != (wanted,):
                raise ValueError("wrong SQL login for initialization operation")
            if request.operation == "migrate":
                configure_defaults(raw, database=request.database, prefix=request.role_prefix)
                migrate(url, connection=connection)
                grant_access(raw, database=request.database, prefix=request.role_prefix)
            if raw.execute("SELECT version_num FROM public.alembic_version").fetchall() != [
                (request.expected_revision,)
            ]:
                raise ValueError("database revision differs from requested revision")
        if request.operation == "migrate":
            return {"status": "complete", "schema_revision": request.expected_revision}
        with tempfile.TemporaryDirectory(prefix="urbanpulse-import-") as temporary:
            directory = Path(temporary)
            captured = LocalCityCapture(directory, capture_city(directory)).read()
            store = CityInputStore(database.engine)
            scope = store.save(
                captured, prepare_import(captured, PostgisMembership(url, engine=database.engine))
            )
            if request.expected_import_id is not None and scope != request.expected_import_id:
                raise ValueError("import differs from requested identity")
            store.select_import(scope)
            if store.active_scope() != scope:
                raise ValueError("active fixture selection differs from verified import")
            return {
                "status": "complete",
                "schema_revision": request.expected_revision,
                "import_id": scope,
            }
    finally:
        database.close()


def child(request: InitializationRequest, deadline: float, output: Connection) -> None:
    report(lambda: execute(request), output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("migrate", "import"))
    parser.add_argument("--database", required=True)
    parser.add_argument("--expected-revision", required=True)
    parser.add_argument("--role-prefix", default="urbanpulse")
    parser.add_argument("--expected-import-id")
    parser.add_argument("--timeout-seconds", type=int, default=540)
    args = parser.parse_args()
    try:
        request = InitializationRequest(**vars(args))
    except ValueError:
        emit({"status": "invalid-job-arguments"})
        return 2
    stop = threading.Event()

    def stopping(signum: int, frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, stopping)
    signal.signal(signal.SIGINT, stopping)
    try:
        result = supervise(request, stop, child)
    except Exception:
        result = {"status": "execution-failed"}
    emit({"operation": request.operation, **result})
    return 0 if result["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())

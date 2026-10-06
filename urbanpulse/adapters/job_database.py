"""Session-bound execution lock: every job read/write uses the locked physical session."""

from typing import Any

import psycopg
from sqlalchemy import event

from urbanpulse.adapters.city_store import engine_for
from urbanpulse.application.durable_delivery import StorageUnavailable

# Database-wide demo mutation lane, shared with future migration/import job runners.
DEMO_JOB_LOCK = (850601, 1)


class JobBusy(RuntimeError):
    pass


class JobSessionLost(StorageUnavailable):
    pass


class JobDatabase:
    def __init__(self, url: str) -> None:
        self.engine = engine_for(url, pool_size=1, max_overflow=0, pool_timeout=1)
        self.connected = False
        event.listen(self.engine, "connect", self._lock)

    def _lock(self, connection: psycopg.Connection[Any], record: Any) -> None:
        # Reconnecting would abandon the lock that guarded earlier transactions.
        if self.connected:
            connection.close()
            raise JobSessionLost("execution session was lost")
        try:
            connection.execute("SET statement_timeout = '10000ms'")
            connection.execute("SET lock_timeout = '3000ms'")
            row = connection.execute("SELECT pg_try_advisory_lock(%s,%s)", DEMO_JOB_LOCK).fetchone()
            if row != (True,):
                raise JobBusy("another demo mutation job is active")
            connection.commit()
            self.connected = True
        except BaseException:
            connection.close()
            raise

    def close(self) -> None:
        # Physical disconnect releases the session lock, including after an error.
        self.engine.dispose()

"""Explicit private database setup; never invoked by application startup.

Callers own transactions and secret handling. New roles start NOLOGIN; bootstrap
refuses existing application roles/tables instead of adopting or rotating them.
"""

import re
from collections.abc import Mapping

from psycopg import Connection, sql

EXPECTED_REVISION = "0007_city_checkpoints"
ROLE_LIMITS = {"runtime": 12, "migrate": 2, "import": 3, "worker": 4}
INPUT_TABLES = (
    "city04_imports",
    "city04_active_imports",
    *(
        f"city04_{domain}_{kind}"
        for domain in ("transport", "weather", "planning")
        for kind in ("revisions", "observations")
    ),
)
EVENT_TABLES = tuple(
    f"event01_{name}"
    for name in (
        "publications",
        "deliveries",
        "attempts",
        "receipts",
        "cursors",
        "replays",
        "probe_effects",
        "city_runs",
        "city_checkpoints",
        "city_inbox",
    )
)
MUTABLE_EVENT_TABLES = (
    "event01_deliveries",
    "event01_attempts",
    "event01_cursors",
    "event01_city_runs",
    "event01_city_checkpoints",
)
APPLICATION_TABLES = (*INPUT_TABLES, *EVENT_TABLES, "alembic_version")


def role_names(prefix: str = "urbanpulse") -> dict[str, str]:
    if re.fullmatch(r"[a-z][a-z0-9_]{0,39}", prefix) is None:
        raise ValueError("invalid database role prefix")
    return {purpose: f"{prefix}_{purpose}" for purpose in ROLE_LIMITS}


def require_database(connection: Connection, expected: str) -> None:
    if connection.autocommit:
        raise ValueError("bootstrap operations require a caller-owned transaction")
    if connection.execute("SELECT current_database()").fetchone() != (expected,):
        raise ValueError("database does not match the explicit target")


def bootstrap(connection: Connection, *, database: str, prefix: str = "urbanpulse") -> None:
    """Initialize an empty application database in the caller's transaction."""
    require_database(connection, database)
    names = role_names(prefix)
    if connection.execute(
        "SELECT 1 FROM pg_roles WHERE rolname = ANY(%s)", (list(names.values()),)
    ).fetchone():
        raise ValueError("application role already exists; inspect, do not rotate or adopt")
    # PostGIS's own reference table is allowed; application/user tables are not.
    if connection.execute(
        "SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename <> 'spatial_ref_sys'"
    ).fetchone():
        raise ValueError("application database is not empty")
    connection.execute("CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA public")
    if connection.execute(
        "SELECT extnamespace = 'public'::regnamespace FROM pg_extension WHERE extname='postgis'"
    ).fetchone() != (True,):
        raise ValueError("PostGIS must be installed in public")
    connection.execute(
        sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(database))
    )
    connection.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
    for purpose, name in names.items():
        connection.execute(
            sql.SQL(
                "CREATE ROLE {} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                "NOREPLICATION NOBYPASSRLS NOINHERIT CONNECTION LIMIT {}"
            ).format(sql.Identifier(name), sql.Literal(ROLE_LIMITS[purpose]))
        )
        connection.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(database), sql.Identifier(name)
            )
        )
        connection.execute(
            sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(name))
        )
        connection.execute(
            sql.SQL("ALTER ROLE {} IN DATABASE {} SET search_path = public").format(
                sql.Identifier(name), sql.Identifier(database)
            )
        )
    connection.execute(
        sql.SQL("GRANT CREATE ON SCHEMA public TO {}").format(sql.Identifier(names["migrate"]))
    )


def activate_roles(
    connection: Connection,
    passwords: Mapping[str, str],
    *,
    database: str,
    prefix: str = "urbanpulse",
) -> None:
    """One-time activation using SCRAM verifiers; passwords must never be logged."""
    require_database(connection, database)
    names = role_names(prefix)
    if set(passwords) != set(names) or any(len(p) < 32 for p in passwords.values()):
        raise ValueError(
            "four independently generated passwords of at least 32 characters required"
        )
    if len(set(passwords.values())) != len(names):
        raise ValueError("passwords must be distinct")
    for purpose, name in names.items():
        row = connection.execute(
            "SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, "
            "rolbypassrls, rolinherit, rolconnlimit FROM pg_roles WHERE rolname=%s",
            (name,),
        ).fetchone()
        if row != (False, False, False, False, False, False, False, ROLE_LIMITS[purpose]):
            raise ValueError("role attributes differ from the unactivated bootstrap profile")
        if connection.execute(
            "SELECT 1 FROM pg_auth_members WHERE member="
            "(SELECT oid FROM pg_roles WHERE rolname=%s)",
            (name,),
        ).fetchone():
            raise ValueError("application role has unexpected membership")
    for purpose, name in names.items():
        verifier = connection.pgconn.encrypt_password(
            passwords[purpose].encode(), name.encode(), b"scram-sha-256"
        ).decode()
        connection.execute(
            sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(name), sql.Literal(verifier)
            )
        )


def require_migrator(connection: Connection, database: str, prefix: str) -> dict[str, str]:
    require_database(connection, database)
    names = role_names(prefix)
    if connection.execute("SELECT current_user").fetchone() != (names["migrate"],):
        raise ValueError("connect as the migration role; application DDL must have that owner")
    return names


def configure_defaults(
    connection: Connection, *, database: str, prefix: str = "urbanpulse"
) -> None:
    """Future objects stay private until their access is explicitly reviewed."""
    require_migrator(connection, database, prefix)
    # Global defaults: schema-scoped REVOKE cannot remove PUBLIC function EXECUTE.
    for kind in ("TABLES", "SEQUENCES", "FUNCTIONS", "TYPES"):
        connection.execute(
            sql.SQL("ALTER DEFAULT PRIVILEGES REVOKE ALL ON {} FROM PUBLIC").format(sql.SQL(kind))
        )


def grant_access(connection: Connection, *, database: str, prefix: str = "urbanpulse") -> None:
    """Apply a closed table allowlist after migrations, with no blanket future grants."""
    names = require_migrator(connection, database, prefix)
    rows = connection.execute(
        "SELECT tablename, tableowner FROM pg_tables WHERE schemaname='public' "
        "AND tablename <> 'spatial_ref_sys'"
    ).fetchall()
    if {r[0] for r in rows} != set(APPLICATION_TABLES) or any(
        r[1] != names["migrate"] for r in rows
    ):
        raise ValueError("unexpected application tables or ownership; review the access matrix")
    if connection.execute("SELECT version_num FROM public.alembic_version").fetchall() != [
        (EXPECTED_REVISION,)
    ]:
        raise ValueError("unexpected migration revision")
    nonowners = sql.SQL(", ").join(
        sql.Identifier(names[k]) for k in ("runtime", "import", "worker")
    )
    for table in APPLICATION_TABLES:
        connection.execute(
            sql.SQL("REVOKE ALL ON TABLE public.{} FROM PUBLIC, {}").format(
                sql.Identifier(table), nonowners
            )
        )

    def grant(privileges: str, table: str, purpose: str) -> None:
        connection.execute(
            sql.SQL("GRANT {} ON TABLE public.{} TO {}").format(
                sql.SQL(privileges), sql.Identifier(table), sql.Identifier(names[purpose])
            )
        )

    for purpose in ("runtime", "import", "worker"):
        for table in INPUT_TABLES:
            grant("SELECT", table, purpose)
        grant("SELECT", "alembic_version", purpose)
    for table in INPUT_TABLES:
        grant("INSERT", table, "import")
    grant("UPDATE", "city04_active_imports", "import")
    for table in EVENT_TABLES:
        grant("SELECT, INSERT", table, "worker")
    for table in MUTABLE_EVENT_TABLES:
        grant("UPDATE", table, "worker")

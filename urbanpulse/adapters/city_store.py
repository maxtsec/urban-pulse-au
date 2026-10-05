"""PostgreSQL owned-domain exports and explicit, atomic fixture import."""

import json
from typing import Any

from pydantic import TypeAdapter
from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    select,
)
from sqlalchemy.engine import Connection, Engine

from urbanpulse.application.capture_replay import payload_hash
from urbanpulse.application.city import CapturedCity
from urbanpulse.application.inputs import CityInputs
from urbanpulse.application.planning_replay import PlanningStep
from urbanpulse.application.weather_replay import WeatherStep
from urbanpulse.contracts.composition import TransportServiceStatusChanged
from urbanpulse.contracts.events import CloudEvent, EventReceipt, VehiclePositionChanged
from urbanpulse.contracts.planning import PlanningSnapshotPublished
from urbanpulse.contracts.weather import ModelledReadingChanged, WeatherWarningChanged

NORMALIZER_VERSION = "city-normalizer-v2"
metadata = MetaData()
imports = Table(
    "city04_imports",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("capture_id", String(64), nullable=False),
    Column("normalizer_version", String(64), nullable=False),
    Column("metadata_json", Text, nullable=False),
    Column("content_hash", String(64), nullable=False),
)
revisions = {}
observations = {}
for owner in ("transport", "weather", "planning"):
    revisions[owner] = Table(
        f"city04_{owner}_revisions",
        metadata,
        Column(
            "scope",
            String(64),
            ForeignKey("city04_imports.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        Column("source", String(200), primary_key=True),
        Column("event_id", String(200), primary_key=True),
        Column("subject", Text, nullable=False),
        Column("revision", Integer, nullable=False),
        Column("fingerprint", String(64), nullable=False),
        Column("envelope", Text, nullable=False),
        UniqueConstraint("scope", "source", "subject", "revision"),
    )
    observations[owner] = Table(
        f"city04_{owner}_observations",
        metadata,
        Column(
            "scope",
            String(64),
            ForeignKey("city04_imports.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        Column("sequence", Integer, primary_key=True),
        Column("seconds", Integer, nullable=False),
        Column("body", Text, nullable=False),
    )

Event = (
    VehiclePositionChanged
    | TransportServiceStatusChanged
    | WeatherWarningChanged
    | ModelledReadingChanged
    | PlanningSnapshotPublished
)
EVENT: TypeAdapter[Event] = TypeAdapter(Event)


def engine_for(url: str) -> Engine:
    return create_engine(
        url.replace("postgresql://", "postgresql+psycopg://", 1),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 3},
        isolation_level="REPEATABLE READ",
        hide_parameters=True,
    )


def encode(value: Any) -> str:
    return json.dumps(
        TypeAdapter(Any).dump_python(value, mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


class DomainExport:
    """Only an owning repository knows its private revision/observation table layout."""

    def __init__(self, owner: str) -> None:
        self.owner = owner

    def write(self, connection: Connection, scope: str, rows: list[dict[str, Any]]) -> None:
        accepted: dict[tuple[str, str], EventReceipt] = {}
        aggregate_revisions: set[tuple[str, str, int]] = set()
        original_wires: dict[tuple[str, str], str] = {}

        def reference(value: Any) -> Any:
            if isinstance(value, CloudEvent):
                receipt = EventReceipt.from_event(value)
                key = (value.source, value.id)
                aggregate = (value.source, value.subject, value.data.revision)
                previous = accepted.get(key)
                if (
                    previous is not None
                    and previous != receipt
                    or previous is None
                    and aggregate in aggregate_revisions
                ):
                    return {"rejected_event": value.model_dump_json()}
                if previous is None:
                    accepted[key] = receipt
                    original_wires[key] = value.model_dump_json()
                    aggregate_revisions.add(aggregate)
                    connection.execute(
                        revisions[self.owner]
                        .insert()
                        .values(
                            scope=scope,
                            source=value.source,
                            event_id=value.id,
                            subject=value.subject,
                            revision=value.data.revision,
                            fingerprint=receipt.fingerprint,
                            envelope=value.model_dump_json(),
                        )
                    )
                event_reference = {"event_reference": [value.source, value.id]}
                if value.model_dump_json() != original_wires[key]:
                    return {**event_reference, "attempt_envelope": value.model_dump_json()}
                return event_reference
            if isinstance(value, dict):
                return {key: reference(item) for key, item in value.items()}
            if isinstance(value, (tuple, list)):
                return [reference(item) for item in value]
            return value

        for sequence, row in enumerate(rows):
            connection.execute(
                observations[self.owner]
                .insert()
                .values(
                    scope=scope,
                    sequence=sequence,
                    seconds=row["frame"]["at_seconds"],
                    body=encode(reference(row)),
                )
            )

    def read(self, connection: Connection, scope: str) -> list[dict[str, Any]]:
        known = {}
        for row in connection.execute(
            select(revisions[self.owner]).where(revisions[self.owner].c.scope == scope)
        ).mappings():
            event = EVENT.validate_json(row["envelope"])
            receipt = EventReceipt.from_event(event)
            if receipt.fingerprint != row["fingerprint"] or (
                event.source,
                event.id,
                event.subject,
                event.data.revision,
            ) != (row["source"], row["event_id"], row["subject"], row["revision"]):
                raise ValueError("persisted event integrity mismatch")
            known[(event.source, event.id)] = event

        def resolve(value: Any) -> Any:
            if isinstance(value, dict):
                if "event_reference" in value:
                    original = known[tuple(value["event_reference"])]
                    if "attempt_envelope" in value:
                        attempt = EVENT.validate_json(value["attempt_envelope"])
                        if EventReceipt.from_event(attempt) != EventReceipt.from_event(original):
                            raise ValueError("attempt does not match its accepted event identity")
                        return attempt
                    return original
                if set(value) == {"rejected_event"}:
                    return EVENT.validate_json(value["rejected_event"])
                return {key: resolve(item) for key, item in value.items()}
            if isinstance(value, list):
                return [resolve(item) for item in value]
            return value

        return [
            resolve(json.loads(body))
            for body in connection.execute(
                select(observations[self.owner].c.body)
                .where(observations[self.owner].c.scope == scope)
                .order_by(observations[self.owner].c.sequence)
            ).scalars()
        ]


class CityInputStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def save(self, captured: CapturedCity, rows: dict[str, list[dict[str, Any]]]) -> str:
        scope = payload_hash([captured.capture_id, NORMALIZER_VERSION])
        info = {
            "boundary": captured.boundary,
            "scenario": {
                key: value
                for key, value in captured.scenario.items()
                if key not in {"frames", "service_frames"}
            },
            "weather": {"outage_at_seconds": captured.weather["outage_at_seconds"]}
            if captured.weather
            else None,
            "planning": {"outage_at_seconds": captured.planning["outage_at_seconds"]}
            if captured.planning
            else None,
        }

        def serializable(value: Any) -> Any:
            if isinstance(value, CloudEvent):
                return value.model_dump(mode="json")
            if isinstance(value, dict):
                return {key: serializable(item) for key, item in value.items()}
            if isinstance(value, (tuple, list)):
                return [serializable(item) for item in value]
            return value

        digest = payload_hash(json.loads(encode([info, serializable(rows)])))
        with (
            self.engine.connect().execution_options(isolation_level="READ COMMITTED") as connection,
            connection.begin(),
        ):
            # Serialize same-import writers before checking its immutable identity.
            connection.exec_driver_sql("SELECT pg_advisory_xact_lock(%s)", (int(scope[:15], 16),))
            existing = connection.execute(
                select(imports.c.content_hash).where(imports.c.id == scope)
            ).scalar_one_or_none()
            if existing is not None:
                if existing != digest:
                    raise ValueError("existing import differs; bump normalizer version")
                return scope
            connection.execute(
                imports.insert().values(
                    id=scope,
                    capture_id=captured.capture_id,
                    normalizer_version=NORMALIZER_VERSION,
                    metadata_json=encode(info),
                    content_hash=digest,
                )
            )
            for owner in ("transport", "weather", "planning"):
                DomainExport(owner).write(connection, scope, rows[owner])
        return scope

    def load(self, scope: str) -> CityInputs:
        with self.engine.connect() as connection, connection.begin():
            row = (
                connection.execute(select(imports).where(imports.c.id == scope))
                .mappings()
                .one_or_none()
            )
            if row is None or row["normalizer_version"] != NORMALIZER_VERSION:
                raise ValueError("city inputs missing; run the explicit fixture import")
            info = json.loads(row["metadata_json"])
            transport = DomainExport("transport").read(connection, scope)
            weather = DomainExport("weather").read(connection, scope)
            planning = DomainExport("planning").read(connection, scope)
            if (
                payload_hash(
                    json.loads(
                        encode(
                            [
                                info,
                                {"transport": transport, "weather": weather, "planning": planning},
                            ]
                        )
                    )
                )
                != row["content_hash"]
            ):
                raise ValueError("persisted input history integrity mismatch")
            scenario = info["scenario"]
            scenario["frames"] = [
                {
                    "at_seconds": item["frame"]["at_seconds"],
                    "event": item["event"].model_dump(mode="json")
                    if item["event"] is not None
                    else item["rejected_header"],
                }
                for item in transport
                if item["kind"] == "position"
            ]
            scenario["service_frames"] = [
                item["frame"] for item in transport if item["kind"] == "service"
            ]
            captured = CapturedCity(
                row["capture_id"], info["boundary"], scenario, info["weather"], info["planning"]
            )
            return CityInputs(
                captured,
                tuple(
                    WeatherStep(
                        item["frame"],
                        item["evidence"],
                        tuple(item["events"]),
                        tuple(item["warning_records"]),
                    )
                    for item in weather
                ),
                tuple(
                    PlanningStep(item["frame"], item["evidence"], item["event"], item["recapture"])
                    for item in planning
                ),
                tuple(item["event"] for item in transport if item["kind"] == "service"),
            )


def migrate(database_url: str) -> None:
    from alembic import command
    from alembic.config import Config

    from urbanpulse.config import ROOT

    config = Config()
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.attributes["database_url"] = database_url
    command.upgrade(config, "head")


def main() -> None:
    import argparse

    from urbanpulse.adapters.city_import import import_fixture
    from urbanpulse.config import Settings

    parser = argparse.ArgumentParser(description="Explicit city schema and fixture setup")
    parser.add_argument("action", choices=("migrate", "import"))
    args = parser.parse_args()
    settings = Settings()
    if args.action == "migrate":
        migrate(settings.database_url)
        print("City schema migrated")
    else:
        print(
            encode(
                {
                    "fixture_import": import_fixture(
                        settings.database_url, settings.city_capture_path
                    )
                }
            )
        )


if __name__ == "__main__":
    main()

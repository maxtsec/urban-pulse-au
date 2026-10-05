"""Location-owned durable run and checkpoint records."""

from sqlalchemy import Column, Integer, MetaData, String, Table, Text

metadata = MetaData()
runs = Table(
    "event01_city_runs",
    metadata,
    Column("id", String(100), primary_key=True),
    Column("scope", String(64)),
    Column("input_hash", String(64)),
    Column("scenario", String(40)),
    Column("boundary_revision", String(64)),
    Column("rule_version", String(100)),
    Column("run_version", String(100)),
    Column("target", Integer),
    Column("completed", Integer),
    Column("last_publication", String(36)),
    Column("last_result_publication", String(36)),
    Column("area_events", Text),
    Column("semantic", Text),
)
checkpoints = Table(
    "event01_city_checkpoints",
    metadata,
    Column("run_id", String(100), primary_key=True),
    Column("seconds", Integer, primary_key=True),
    Column("status", String(20)),
    Column("manifest", Text),
    Column("publications", Text),
    Column("result", Text),
    Column("error", Text),
)
inbox = Table(
    "event01_city_inbox",
    metadata,
    Column("run_id", String(100), primary_key=True),
    Column("consumer", String(200), primary_key=True),
    Column("source", Text, primary_key=True),
    Column("event_id", Text, primary_key=True),
    Column("envelope", Text),
)

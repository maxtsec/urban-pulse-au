"""Private PostgreSQL outbox and consumer-ledger tables."""

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)

metadata = MetaData()
publications = Table(
    "event01_publications",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("context", String(200), nullable=False),
    Column("source", Text, nullable=False),
    Column("event_id", Text, nullable=False),
    Column("subject", Text, nullable=False),
    Column("revision", BigInteger, nullable=False),
    Column("fingerprint", String(64), nullable=False),
    Column("envelope", Text, nullable=False),
    Column("consumers", Text, nullable=False),
    Column(
        "created_at", DateTime(timezone=True), nullable=False, server_default=func.clock_timestamp()
    ),
    UniqueConstraint("context", "source", "event_id"),
    UniqueConstraint("context", "source", "subject", "revision"),
)
deliveries = Table(
    "event01_deliveries",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("publication_id", String(36), ForeignKey("event01_publications.id"), nullable=False),
    Column("consumer", String(200), nullable=False),
    Column("predecessor_id", String(36), ForeignKey("event01_deliveries.id")),
    Column("status", String(20), nullable=False),
    Column("generation", Integer, nullable=False),
    Column("attempt_count", Integer, nullable=False),
    Column("lease_until", DateTime(timezone=True)),
    Column(
        "available_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.clock_timestamp(),
    ),
    Column("outcome", String(30)),
    Column(
        "created_at", DateTime(timezone=True), nullable=False, server_default=func.clock_timestamp()
    ),
    UniqueConstraint("publication_id", "consumer"),
)
attempts = Table(
    "event01_attempts",
    metadata,
    Column("delivery_id", String(36), ForeignKey("event01_deliveries.id"), primary_key=True),
    Column("generation", Integer, primary_key=True),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("lease_until", DateTime(timezone=True), nullable=False),
    Column("ended_at", DateTime(timezone=True)),
    Column("outcome", String(30)),
)
receipts = Table(
    "event01_receipts",
    metadata,
    Column("context", String(200), primary_key=True),
    Column("consumer", String(200), primary_key=True),
    Column("source", Text, primary_key=True),
    Column("event_id", Text, primary_key=True),
    Column("subject", Text, nullable=False),
    Column("revision", BigInteger, nullable=False),
    Column("fingerprint", String(64), nullable=False),
    Column("outcome", String(30), nullable=False),
)
cursors = Table(
    "event01_cursors",
    metadata,
    Column("context", String(200), primary_key=True),
    Column("consumer", String(200), primary_key=True),
    Column("source", Text, primary_key=True),
    Column("subject", Text, primary_key=True),
    Column("event_id", Text, nullable=False),
    Column("revision", BigInteger, nullable=False),
    Column("fingerprint", String(64), nullable=False),
)

replays = Table(
    "event01_replays",
    metadata,
    Column("delivery_id", String(36), ForeignKey("event01_deliveries.id"), primary_key=True),
    Column("generation", Integer, primary_key=True),
    Column("reason", String(40), nullable=False),
    Column(
        "requested_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.clock_timestamp(),
    ),
)
probe_effects = Table(
    "event01_probe_effects",
    metadata,
    Column("context", String(200), primary_key=True),
    Column("source", Text, primary_key=True),
    Column("event_id", Text, primary_key=True),
    Column(
        "applied_at", DateTime(timezone=True), nullable=False, server_default=func.clock_timestamp()
    ),
)

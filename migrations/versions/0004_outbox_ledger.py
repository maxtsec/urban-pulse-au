"""Add publication intent, per-consumer claims and atomic receipt storage."""

from alembic import op

revision = "0004_outbox_ledger"
down_revision = "0003_observation_codec"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE event01_publications (
            id varchar(36) PRIMARY KEY, context varchar(200) NOT NULL,
            source text NOT NULL, event_id text NOT NULL, subject text NOT NULL,
            revision bigint NOT NULL CHECK (revision > 0), fingerprint varchar(64) NOT NULL,
            envelope text NOT NULL, consumers text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            UNIQUE (context, source, event_id), UNIQUE (context, source, subject, revision)
        )
    """)
    op.execute("""
        CREATE TABLE event01_deliveries (
            id varchar(36) PRIMARY KEY,
            publication_id varchar(36) NOT NULL REFERENCES event01_publications(id),
            consumer varchar(200) NOT NULL,
            status varchar(20) NOT NULL
                CHECK (status IN ('pending','leased','complete','dead-letter')),
            generation integer NOT NULL CHECK (generation >= 0),
            attempt_count integer NOT NULL CHECK (attempt_count BETWEEN 0 AND 3),
            lease_until timestamptz, outcome varchar(30),
            created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            UNIQUE (publication_id, consumer),
            CHECK ((status = 'leased') = (lease_until IS NOT NULL))
        )
    """)
    op.execute("""
        CREATE INDEX event01_claimable ON event01_deliveries (consumer, created_at, id)
        WHERE status IN ('pending','leased')
    """)
    op.execute("""
        CREATE TABLE event01_attempts (
            delivery_id varchar(36) REFERENCES event01_deliveries(id),
            generation integer NOT NULL CHECK (generation > 0),
            started_at timestamptz NOT NULL, lease_until timestamptz NOT NULL,
            ended_at timestamptz, outcome varchar(30), PRIMARY KEY (delivery_id, generation)
        )
    """)
    op.execute("""
        CREATE TABLE event01_receipts (
            context varchar(200), consumer varchar(200), source text, event_id text,
            subject text NOT NULL, revision bigint NOT NULL CHECK (revision > 0),
            fingerprint varchar(64) NOT NULL,
            outcome varchar(30) NOT NULL CHECK (outcome IN ('apply','superseded')),
            PRIMARY KEY (context, consumer, source, event_id)
        )
    """)
    op.execute("""
        CREATE TABLE event01_cursors (
            context varchar(200), consumer varchar(200), source text, subject text,
            event_id text NOT NULL, revision bigint NOT NULL CHECK (revision > 0),
            fingerprint varchar(64) NOT NULL,
            PRIMARY KEY (context, consumer, source, subject)
        )
    """)


def downgrade() -> None:
    # Explicit downgrade intentionally removes this delivery subsystem's records.
    for name in ("cursors", "receipts", "attempts", "deliveries", "publications"):
        op.drop_table(f"event01_{name}")

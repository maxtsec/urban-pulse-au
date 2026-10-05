"""Persist retry times, operator replay audit and synthetic recovery effects."""

from alembic import op

revision = "0006_worker_recovery"
down_revision = "0005_attempt_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE event01_deliveries ADD available_at timestamptz "
        "NOT NULL DEFAULT clock_timestamp()"
    )
    op.drop_constraint("event01_deliveries_status_check", "event01_deliveries", type_="check")
    op.create_check_constraint(
        "event01_deliveries_status_check",
        "event01_deliveries",
        "status IN ('pending','leased','retry','complete','dead-letter')",
    )
    op.execute("DROP INDEX event01_claimable")
    op.execute(
        "CREATE INDEX event01_claimable ON event01_deliveries "
        "(consumer, available_at, created_at, id) WHERE status IN ('pending','leased','retry')"
    )
    op.execute("""
        CREATE TABLE event01_replays (
            delivery_id varchar(36) REFERENCES event01_deliveries(id),
            generation integer CHECK (generation > 0), reason varchar(40) NOT NULL,
            requested_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (delivery_id, generation),
            CHECK (reason IN ('operator-retry','handler-fixed','verify-deduplication'))
        )
    """)
    op.execute("""
        CREATE TABLE event01_probe_effects (
            context varchar(200), source text, event_id text,
            applied_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (context, source, event_id)
        )
    """)


def downgrade() -> None:
    # Never discard operator history or scheduled retries implicitly.
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM event01_replays)
               OR EXISTS (SELECT 1 FROM event01_probe_effects)
               OR EXISTS (SELECT 1 FROM event01_deliveries WHERE status = 'retry') THEN
                RAISE EXCEPTION 'worker recovery data prevents downgrade';
            END IF;
        END $$
    """)
    op.drop_table("event01_probe_effects")
    op.drop_table("event01_replays")
    op.execute("DROP INDEX event01_claimable")
    op.execute(
        "CREATE INDEX event01_claimable ON event01_deliveries "
        "(consumer, created_at, id) WHERE status IN ('pending','leased')"
    )
    op.drop_constraint("event01_deliveries_status_check", "event01_deliveries", type_="check")
    op.create_check_constraint(
        "event01_deliveries_status_check",
        "event01_deliveries",
        "status IN ('pending','leased','complete','dead-letter')",
    )
    op.drop_column("event01_deliveries", "available_at")

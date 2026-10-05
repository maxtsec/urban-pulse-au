"""Persist independently advanced city runs, ordered input barriers and checkpoint results."""

from alembic import op

revision = "0007_city_checkpoints"
down_revision = "0006_worker_recovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE event01_deliveries ADD predecessor_id varchar(36) "
        "REFERENCES event01_deliveries(id)"
    )
    op.execute("""
        CREATE TABLE event01_city_runs (
            id varchar(100) PRIMARY KEY, scope varchar(64) NOT NULL REFERENCES city04_imports(id),
            input_hash varchar(64) NOT NULL,
            scenario varchar(40) NOT NULL, boundary_revision varchar(64) NOT NULL,
            rule_version varchar(100) NOT NULL, run_version varchar(100) NOT NULL,
            target integer NOT NULL DEFAULT -1 CHECK (target BETWEEN -1 AND 360),
            completed integer NOT NULL DEFAULT -1 CHECK (completed BETWEEN -1 AND 360),
            last_publication varchar(36), last_result_publication varchar(36),
            area_events text NOT NULL DEFAULT '[]',
            semantic text, CHECK (completed <= target)
        )
    """)
    op.execute("""
        CREATE TABLE event01_city_checkpoints (
            run_id varchar(100) REFERENCES event01_city_runs(id), seconds integer,
            status varchar(20) NOT NULL CHECK (status IN ('scheduled','pending','complete')),
            manifest text NOT NULL, publications text NOT NULL DEFAULT '[]',
            result text, error text,
            PRIMARY KEY (run_id, seconds), CHECK (seconds BETWEEN 0 AND 360),
            CHECK ((status = 'complete') = (result IS NOT NULL))
        )
    """)
    op.execute("""
        CREATE TABLE event01_city_inbox (
            run_id varchar(100) REFERENCES event01_city_runs(id), consumer varchar(200),
            source text, event_id text, envelope text NOT NULL,
            PRIMARY KEY (run_id, consumer, source, event_id)
        )
    """)


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM event01_city_runs)
               OR EXISTS (SELECT 1 FROM event01_deliveries WHERE predecessor_id IS NOT NULL) THEN
                RAISE EXCEPTION 'city checkpoint history prevents downgrade';
            END IF;
        END $$
    """)
    op.drop_table("event01_city_inbox")
    op.drop_table("event01_city_checkpoints")
    op.drop_table("event01_city_runs")
    op.drop_column("event01_deliveries", "predecessor_id")

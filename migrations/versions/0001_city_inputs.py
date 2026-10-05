"""Persist owned fixture inputs for repeatable in-process reconstruction."""

import sqlalchemy as sa
from alembic import op

revision = "0001_city_inputs"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "city04_imports",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("capture_id", sa.String(64), nullable=False),
        sa.Column("normalizer_version", sa.String(64), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
    )
    for owner in ("transport", "weather", "planning"):
        op.create_table(
            f"city04_{owner}_revisions",
            sa.Column(
                "scope",
                sa.String(64),
                sa.ForeignKey("city04_imports.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("source", sa.String(200), primary_key=True),
            sa.Column("event_id", sa.String(200), primary_key=True),
            sa.Column("subject", sa.Text(), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("fingerprint", sa.String(64), nullable=False),
            sa.Column("envelope", sa.Text(), nullable=False),
            sa.UniqueConstraint("scope", "source", "subject", "revision"),
        )
        op.create_table(
            f"city04_{owner}_observations",
            sa.Column(
                "scope",
                sa.String(64),
                sa.ForeignKey("city04_imports.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("sequence", sa.Integer(), primary_key=True),
            sa.Column("seconds", sa.Integer(), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
        )


def downgrade() -> None:
    for owner in ("transport", "weather", "planning"):
        op.drop_table(f"city04_{owner}_observations")
        op.drop_table(f"city04_{owner}_revisions")
    op.drop_table("city04_imports")

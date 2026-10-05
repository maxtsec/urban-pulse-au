"""Select a completed fixture import independently of API host files."""

import sqlalchemy as sa
from alembic import op

revision = "0002_active_import"
down_revision = "0001_city_inputs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "city04_active_imports",
        sa.Column("name", sa.String(100), primary_key=True),
        sa.Column("scope", sa.String(64), sa.ForeignKey("city04_imports.id"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("city04_active_imports")

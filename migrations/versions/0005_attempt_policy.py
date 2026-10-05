"""Keep retry policy in the application while preserving nonnegative counters."""

from alembic import op

revision = "0005_attempt_policy"
down_revision = "0004_outbox_ledger"
branch_labels = None
depends_on = None

CONSTRAINT = "event01_deliveries_attempt_count_check"


def upgrade() -> None:
    op.drop_constraint(CONSTRAINT, "event01_deliveries", type_="check")
    op.create_check_constraint(CONSTRAINT, "event01_deliveries", "attempt_count >= 0")


def downgrade() -> None:
    # Fails transactionally if a later policy has already allowed more attempts.
    op.drop_constraint(CONSTRAINT, "event01_deliveries", type_="check")
    op.create_check_constraint(CONSTRAINT, "event01_deliveries", "attempt_count BETWEEN 0 AND 3")

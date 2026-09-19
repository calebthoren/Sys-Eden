"""Baseline version marker; domain tables arrive with their owning milestones."""

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Establish Alembic version tracking without speculative domain tables."""


def downgrade() -> None:
    """No domain tables exist in the baseline."""

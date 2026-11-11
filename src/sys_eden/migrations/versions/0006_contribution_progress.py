"""Track material conversation contributions independently of transcript summaries."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("report_conversation_links", sa.Column(
        "contribution_through_sequence", sa.Integer(), nullable=False, server_default="0"
    ))
    op.add_column("report_conversation_links", sa.Column(
        "contribution_updated_at", sa.Text(), nullable=True
    ))


def downgrade() -> None:
    op.drop_column("report_conversation_links", "contribution_updated_at")
    op.drop_column("report_conversation_links", "contribution_through_sequence")

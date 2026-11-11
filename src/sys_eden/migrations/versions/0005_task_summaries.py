"""Add compact terminal-task summaries and task/conversation associations."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("final_summary", sa.Text(), nullable=True))
    op.create_table(
        "task_conversation_links",
        sa.Column(
            "task_id",
            sa.String(length=100),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        # Temporary conversations intentionally never enter SQLite, so this identity
        # cannot use a foreign key until a TMP conversation is explicitly saved.
        sa.Column("conversation_id", sa.String(length=100), primary_key=True),
        sa.Column("relationship_role", sa.String(length=20), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "relationship_role IN ('primary', 'supporting')",
            name="ck_task_conversation_role",
        ),
    )
    op.create_index(
        "uq_task_primary_conversation",
        "task_conversation_links",
        ["task_id"],
        unique=True,
        sqlite_where=sa.text("relationship_role = 'primary'"),
    )
    op.create_index(
        "ix_task_conversation_conversation",
        "task_conversation_links",
        ["conversation_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_task_conversation_conversation", table_name="task_conversation_links"
    )
    op.drop_index("uq_task_primary_conversation", table_name="task_conversation_links")
    op.drop_table("task_conversation_links")
    op.drop_column("tasks", "final_summary")

"""Saved conversations, messages, report links, and retention reviews."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(length=100), primary_key=True),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("persistence", sa.String(length=20), nullable=False),
        sa.Column("transcript_state", sa.String(length=20), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_resumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rolling_summary", sa.Text(), nullable=True),
        sa.Column("summary_through_sequence", sa.Integer(), nullable=False),
        sa.Column("retention_policy", sa.String(length=200), nullable=True),
        sa.Column("last_message_sequence", sa.Integer(), nullable=False),
        sa.Column("generated_test_data", sa.Boolean(), nullable=False),
        sa.CheckConstraint("schema_version >= 1", name="ck_conversations_schema_version"),
        sa.CheckConstraint("revision >= 1", name="ck_conversations_revision"),
        sa.CheckConstraint("persistence = 'saved'", name="ck_conversations_saved_only"),
        sa.CheckConstraint(
            "transcript_state IN ('full', 'compact', 'deleted')",
            name="ck_conversations_transcript_state",
        ),
        sa.CheckConstraint(
            "summary_through_sequence >= 0", name="ck_conversations_summary_sequence"
        ),
        sa.CheckConstraint(
            "last_message_sequence >= 0", name="ck_conversations_message_sequence"
        ),
    )
    op.create_index(
        "ix_conversations_updated_at", "conversations", ["updated_at"]
    )
    op.create_index(
        "ix_conversations_state_pinned",
        "conversations",
        ["transcript_state", "pinned"],
    )
    op.create_table(
        "conversation_messages",
        sa.Column(
            "conversation_id",
            sa.String(length=100),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("sequence", sa.Integer(), primary_key=True),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retained_in_compact", sa.Boolean(), nullable=False),
        sa.Column("generated_test_data", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.CheckConstraint("role IN ('user', 'eden')", name="ck_conversation_message_role"),
        sa.CheckConstraint("sequence >= 1", name="ck_conversation_message_sequence"),
    )
    op.create_index(
        "ix_conversation_messages_created_at",
        "conversation_messages",
        ["conversation_id", "created_at"],
    )
    op.create_table(
        "report_conversation_links",
        sa.Column(
            "report_id",
            sa.String(length=100),
            sa.ForeignKey("reports.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "conversation_id",
            sa.String(length=100),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("relationship_role", sa.String(length=20), nullable=False),
        sa.Column("contribution_summary", sa.Text(), nullable=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("linked_by", sa.String(length=20), nullable=False),
        sa.CheckConstraint(
            "relationship_role IN ('primary', 'related')",
            name="ck_report_conversation_role",
        ),
        sa.CheckConstraint(
            "linked_by IN ('user', 'eden')", name="ck_report_conversation_linked_by"
        ),
    )
    op.create_index(
        "uq_report_conversation_primary",
        "report_conversation_links",
        ["conversation_id"],
        unique=True,
        sqlite_where=sa.text("relationship_role = 'primary'"),
    )
    op.create_index(
        "ix_report_conversation_conversation",
        "report_conversation_links",
        ["conversation_id"],
    )
    op.create_table(
        "standalone_conversation_contributions",
        sa.Column("id", sa.String(length=100), primary_key=True),
        sa.Column(
            "report_id",
            sa.String(length=100),
            sa.ForeignKey("reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_temporary_conversation_id", sa.String(length=100), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("transcript_retained", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "transcript_retained = 0", name="ck_standalone_contribution_no_transcript"
        ),
    )
    op.create_index(
        "ix_standalone_contribution_report",
        "standalone_conversation_contributions",
        ["report_id", "created_at"],
    )
    op.create_table(
        "conversation_retention_candidates",
        sa.Column(
            "report_id",
            sa.String(length=100),
            sa.ForeignKey("reports.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "conversation_id",
            sa.String(length=100),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("eligible", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("conversation_retention_candidates")
    op.drop_index(
        "ix_standalone_contribution_report",
        table_name="standalone_conversation_contributions",
    )
    op.drop_table("standalone_conversation_contributions")
    op.drop_index(
        "ix_report_conversation_conversation", table_name="report_conversation_links"
    )
    op.drop_index("uq_report_conversation_primary", table_name="report_conversation_links")
    op.drop_table("report_conversation_links")
    op.drop_index(
        "ix_conversation_messages_created_at", table_name="conversation_messages"
    )
    op.drop_table("conversation_messages")
    op.drop_index("ix_conversations_state_pinned", table_name="conversations")
    op.drop_index("ix_conversations_updated_at", table_name="conversations")
    op.drop_table("conversations")

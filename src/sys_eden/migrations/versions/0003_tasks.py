"""Durable Core runtime sessions, tasks, events, and checkpoints."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


TASK_STATES = (
    "'created', 'observing', 'awaiting_clarification', 'researching', 'diagnosing', "
    "'planning', 'awaiting_approval', 'executing', 'verifying', 'monitoring', 'paused', "
    "'waiting_condition', 'waiting_user', 'recovery_required', 'completed', 'failed', "
    "'canceled'"
)


def upgrade() -> None:
    op.create_table(
        "core_runtime_sessions",
        sa.Column("id", sa.String(length=100), primary_key=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stop_reason", sa.String(length=50), nullable=True),
        sa.Column("interrupted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'clean_stopped', 'interrupted')",
            name="ck_core_runtime_session_status",
        ),
    )
    op.create_index(
        "ix_core_runtime_sessions_started_at", "core_runtime_sessions", ["started_at"]
    )
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=100), primary_key=True),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("origin", sa.String(length=30), nullable=False),
        sa.Column("state", sa.String(length=40), nullable=False),
        sa.Column("resume_state", sa.String(length=40), nullable=True),
        sa.Column("control_request", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active_elapsed_seconds", sa.Float(), nullable=False),
        sa.Column("progress_json", sa.Text(), nullable=True),
        sa.Column(
            "active_report_id",
            sa.String(length=100),
            sa.ForeignKey("reports.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "runtime_session_id",
            sa.String(length=100),
            sa.ForeignKey("core_runtime_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("last_event_sequence", sa.Integer(), nullable=False),
        sa.Column("last_checkpoint_sequence", sa.Integer(), nullable=False),
        sa.CheckConstraint("schema_version >= 1", name="ck_tasks_schema_version"),
        sa.CheckConstraint("revision >= 1", name="ck_tasks_revision"),
        sa.CheckConstraint("active_elapsed_seconds >= 0", name="ck_tasks_elapsed"),
        sa.CheckConstraint("last_event_sequence >= 0", name="ck_tasks_event_sequence"),
        sa.CheckConstraint(
            "last_checkpoint_sequence >= 0", name="ck_tasks_checkpoint_sequence"
        ),
        sa.CheckConstraint(
            "origin IN ('user', 'system', 'synthetic_test')", name="ck_tasks_origin"
        ),
        sa.CheckConstraint(f"state IN ({TASK_STATES})", name="ck_tasks_state"),
        sa.CheckConstraint(
            f"resume_state IS NULL OR resume_state IN ({TASK_STATES})",
            name="ck_tasks_resume_state",
        ),
        sa.CheckConstraint(
            "control_request IS NULL OR control_request IN ('pause', 'cancel')",
            name="ck_tasks_control_request",
        ),
    )
    op.create_index("ix_tasks_state_updated", "tasks", ["state", "updated_at"])
    op.create_index("ix_tasks_runtime_session", "tasks", ["runtime_session_id"])
    op.create_table(
        "task_events",
        sa.Column("id", sa.String(length=100), primary_key=True),
        sa.Column(
            "task_id",
            sa.String(length=100),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("from_state", sa.String(length=40), nullable=True),
        sa.Column("to_state", sa.String(length=40), nullable=True),
        sa.Column("progress_json", sa.Text(), nullable=True),
        sa.Column("runtime_session_id", sa.String(length=100), nullable=True),
        sa.Column("generated_test_data", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("task_id", "sequence", name="uq_task_event_sequence"),
    )
    op.create_index("ix_task_events_task_time", "task_events", ["task_id", "occurred_at"])
    op.create_table(
        "task_checkpoints",
        sa.Column("id", sa.String(length=100), primary_key=True),
        sa.Column(
            "task_id",
            sa.String(length=100),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=40), nullable=False),
        sa.Column("state", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_json", sa.Text(), nullable=False),
        sa.Column("generated_test_data", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("task_id", "sequence", name="uq_task_checkpoint_sequence"),
    )
    op.create_index(
        "ix_task_checkpoints_task_time", "task_checkpoints", ["task_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_task_checkpoints_task_time", table_name="task_checkpoints")
    op.drop_table("task_checkpoints")
    op.drop_index("ix_task_events_task_time", table_name="task_events")
    op.drop_table("task_events")
    op.drop_index("ix_tasks_runtime_session", table_name="tasks")
    op.drop_index("ix_tasks_state_updated", table_name="tasks")
    op.drop_table("tasks")
    op.drop_index("ix_core_runtime_sessions_started_at", table_name="core_runtime_sessions")
    op.drop_table("core_runtime_sessions")

"""Structured reports and knowledge-history tables."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_chains",
        sa.Column("id", sa.String(length=100), primary_key=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "reports",
        sa.Column("id", sa.String(length=100), primary_key=True),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("activity", sa.String(length=30), nullable=True),
        sa.Column("trigger", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "primary_chain_id",
            sa.String(length=100),
            sa.ForeignKey("report_chains.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.CheckConstraint("schema_version >= 1", name="ck_reports_schema_version"),
        sa.CheckConstraint("revision >= 1", name="ck_reports_revision"),
        sa.CheckConstraint("state IN ('open', 'closed')", name="ck_reports_state"),
        sa.CheckConstraint(
            "status IN ('active', 'resolved', 'failed', 'archived', 'canceled')",
            name="ck_reports_status",
        ),
        sa.CheckConstraint(
            "priority IN ('low', 'normal', 'high', 'critical')",
            name="ck_reports_priority",
        ),
    )
    op.create_index("ix_reports_updated_at", "reports", ["updated_at"])
    op.create_index("ix_reports_state_status", "reports", ["state", "status"])
    op.create_table(
        "report_tags",
        sa.Column(
            "report_id",
            sa.String(length=100),
            sa.ForeignKey("reports.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("category", sa.String(length=20), primary_key=True),
        sa.Column("value", sa.String(length=100), primary_key=True),
        sa.CheckConstraint("category IN ('purpose', 'component')", name="ck_report_tags_category"),
    )
    op.create_index("ix_report_tags_lookup", "report_tags", ["category", "value"])
    op.create_table(
        "report_observations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "report_id",
            sa.String(length=100),
            sa.ForeignKey("reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("report_id", "position", name="uq_report_observation_position"),
    )
    op.create_table(
        "report_hypotheses",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "report_id",
            sa.String(length=100),
            sa.ForeignKey("reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("report_id", "position", name="uq_report_hypothesis_position"),
    )
    op.create_table(
        "report_evidence",
        sa.Column("id", sa.String(length=100), primary_key=True),
        sa.Column(
            "report_id",
            sa.String(length=100),
            sa.ForeignKey("reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("evidence_type", sa.String(length=100), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("reference", sa.Text(), nullable=True),
        sa.Column("sensitivity", sa.String(length=100), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("report_id", "position", name="uq_report_evidence_position"),
    )
    op.create_table(
        "report_confidence_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "report_id",
            sa.String(length=100),
            sa.ForeignKey("reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("checkpoint", sa.String(length=100), nullable=False),
        sa.Column("diagnostic", sa.Float(), nullable=True),
        sa.Column("research", sa.Float(), nullable=True),
        sa.Column("execution", sa.Float(), nullable=True),
        sa.Column("safety", sa.Float(), nullable=True),
        sa.Column("overall", sa.Float(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("report_id", "position", name="uq_report_confidence_position"),
    )
    op.create_table(
        "report_verifications",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "report_id",
            sa.String(length=100),
            sa.ForeignKey("reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("success_criteria", sa.Text(), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("verdict", sa.String(length=20), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("evidence_ids_json", sa.Text(), nullable=False),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("report_id", "position", name="uq_report_verification_position"),
    )
    op.create_table(
        "report_relationships",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "source_report_id",
            sa.String(length=100),
            sa.ForeignKey("reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_report_id",
            sa.String(length=100),
            sa.ForeignKey("reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relationship_type", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_report_id <> target_report_id", name="ck_report_relationship_not_self"
        ),
        sa.UniqueConstraint(
            "source_report_id",
            "target_report_id",
            "relationship_type",
            name="uq_report_relationship",
        ),
    )
    op.create_index("ix_report_relationship_target", "report_relationships", ["target_report_id"])


def downgrade() -> None:
    op.drop_index("ix_report_relationship_target", table_name="report_relationships")
    op.drop_table("report_relationships")
    op.drop_table("report_verifications")
    op.drop_table("report_confidence_history")
    op.drop_table("report_evidence")
    op.drop_table("report_hypotheses")
    op.drop_table("report_observations")
    op.drop_index("ix_report_tags_lookup", table_name="report_tags")
    op.drop_table("report_tags")
    op.drop_index("ix_reports_state_status", table_name="reports")
    op.drop_index("ix_reports_updated_at", table_name="reports")
    op.drop_table("reports")
    op.drop_table("report_chains")

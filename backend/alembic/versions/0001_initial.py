"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False, server_default="analyst"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("module_key", sa.String(64), nullable=False),
        sa.Column("module_version", sa.String(32), nullable=False, server_default="1.0.0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="created"),
        sa.Column("triggered_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("options", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_runs_module_key", "runs", ["module_key"])
    op.create_index("ix_runs_status", "runs", ["status"])

    op.create_table(
        "run_files",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("slot", sa.String(64), nullable=False),
        sa.Column("original_filename", sa.String(512), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("storage_path", sa.String(1024), nullable=False),
        sa.Column("validation_ok", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("validation_note", sa.String(512), nullable=True),
    )
    op.create_index("ix_run_files_run_id", "run_files", ["run_id"])

    op.create_table(
        "run_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("sheet_name", sa.String(128), nullable=False),
        sa.Column("row_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("payload", sa.JSON, nullable=False, server_default="{}"),
    )
    op.create_index("ix_run_results_run_id", "run_results", ["run_id"])
    op.create_index("ix_run_results_kind", "run_results", ["kind"])

    op.create_table(
        "run_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("from_status", sa.String(32), nullable=False),
        sa.Column("to_status", sa.String(32), nullable=False),
        sa.Column("message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_run_events_run_id", "run_events", ["run_id"])

    op.create_table(
        "run_artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False, server_default="excel_report"),
        sa.Column("storage_path", sa.String(1024), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_run_artifacts_run_id", "run_artifacts", ["run_id"])


def downgrade() -> None:
    op.drop_table("run_artifacts")
    op.drop_table("run_events")
    op.drop_table("run_results")
    op.drop_table("run_files")
    op.drop_table("runs")
    op.drop_table("users")

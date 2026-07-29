"""api keys, module configs, recurring schedules, exception annotations

Revision ID: 0002_api_keys_module_configs_schedules
Revises: 0001_initial
Create Date: 2026-07-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_api_keys_module_configs_schedules"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # batch mode: SQLite can't ALTER a column in with an FK constraint in
    # place, only recreate-and-copy the table (which batch mode handles);
    # Postgres/MySQL run these same ops directly, batch mode is a no-op there.
    with op.batch_alter_table("run_results") as batch_op:
        batch_op.add_column(sa.Column("annotation_status", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("annotation_note", sa.Text, nullable=True))
        batch_op.add_column(
            sa.Column(
                "annotation_by",
                sa.String(36),
                sa.ForeignKey("users.id", name="fk_run_results_annotation_by_users"),
                nullable=True,
            )
        )
        batch_op.add_column(sa.Column("annotation_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("key_prefix", sa.String(12), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"], unique=True)

    op.create_table(
        "module_configs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("module_key", sa.String(64), nullable=False),
        sa.Column("default_options", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_module_configs_module_key", "module_configs", ["module_key"], unique=True)

    op.create_table(
        "recurring_schedules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("module_key", sa.String(64), nullable=False),
        sa.Column("source_run_id", sa.String(36), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("interval_minutes", sa.Integer, nullable=False, server_default="1440"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("last_fired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_id", sa.String(36), sa.ForeignKey("runs.id"), nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_recurring_schedules_module_key", "recurring_schedules", ["module_key"])


def downgrade() -> None:
    op.drop_table("recurring_schedules")
    op.drop_table("module_configs")
    op.drop_table("api_keys")
    with op.batch_alter_table("run_results") as batch_op:
        batch_op.drop_column("annotation_at")
        batch_op.drop_column("annotation_by")
        batch_op.drop_column("annotation_note")
        batch_op.drop_column("annotation_status")

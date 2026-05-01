"""agent instructions

Revision ID: 0002_agent_instructions
Revises: 0001_initial_schema
Create Date: 2026-05-01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_agent_instructions"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_instructions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("scope", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="approved"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_instructions_scope", "agent_instructions", ["scope"])
    op.create_index(
        "ix_agent_instructions_scope_status_priority",
        "agent_instructions",
        ["scope", "status", "priority"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_instructions_scope_status_priority", table_name="agent_instructions")
    op.drop_index("ix_agent_instructions_scope", table_name="agent_instructions")
    op.drop_table("agent_instructions")

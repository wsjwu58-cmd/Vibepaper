"""control plane: approvals, wakeup notices, action audit columns

Revision ID: 001_control_plane
Revises:
Create Date: 2026-08-27
"""
from alembic import op
import sqlalchemy as sa

revision = "001_control_plane"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE user_memories ADD COLUMN IF NOT EXISTS tenant_id BIGINT")
    op.execute("ALTER TABLE user_memories ADD COLUMN IF NOT EXISTS canvas_id BIGINT")
    op.execute("ALTER TABLE user_memories ADD COLUMN IF NOT EXISTS visibility VARCHAR(16) DEFAULT 'user'")
    op.execute("ALTER TABLE user_memories ADD COLUMN IF NOT EXISTS source VARCHAR(64) DEFAULT 'user'")
    op.execute("ALTER TABLE user_memories ADD COLUMN IF NOT EXISTS confidence DOUBLE PRECISION DEFAULT 1.0")
    op.execute("ALTER TABLE user_memories ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ")
    op.execute("ALTER TABLE user_memories ADD COLUMN IF NOT EXISTS deleted BOOLEAN DEFAULT false")
    op.execute("ALTER TABLE user_memories ADD COLUMN IF NOT EXISTS scope VARCHAR(16) DEFAULT 'long_term'")
    op.execute("ALTER TABLE user_memories ADD COLUMN IF NOT EXISTS embedding JSONB DEFAULT '[]'::jsonb")
    op.execute("ALTER TABLE user_memories ADD COLUMN IF NOT EXISTS last_merged_at TIMESTAMPTZ")
    op.execute("ALTER TABLE session_fragments ADD COLUMN IF NOT EXISTS fragment_type VARCHAR(32) DEFAULT 'worldview'")
    op.execute("ALTER TABLE session_fragments ADD COLUMN IF NOT EXISTS canvas_id BIGINT")
    op.execute("ALTER TABLE skills ADD COLUMN IF NOT EXISTS category VARCHAR(32) DEFAULT 'general'")

    op.execute("ALTER TABLE agent_actions ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(128)")
    op.execute("ALTER TABLE agent_actions ADD COLUMN IF NOT EXISTS plan_version INTEGER DEFAULT 1")
    op.execute("ALTER TABLE agent_actions ADD COLUMN IF NOT EXISTS step_id VARCHAR(64)")
    op.execute("ALTER TABLE agent_actions ADD COLUMN IF NOT EXISTS approval_id BIGINT")
    op.execute("ALTER TABLE agent_actions ADD COLUMN IF NOT EXISTS attempt_no INTEGER DEFAULT 1")
    op.execute("ALTER TABLE agent_actions ADD COLUMN IF NOT EXISTS parent_action_id BIGINT")
    op.execute("ALTER TABLE agent_actions ADD COLUMN IF NOT EXISTS estimated_cost INTEGER DEFAULT 0")
    op.execute("ALTER TABLE agent_actions ADD COLUMN IF NOT EXISTS approved_cost_cap INTEGER")
    op.execute("ALTER TABLE agent_actions ADD COLUMN IF NOT EXISTS task_id VARCHAR(64)")
    op.execute("ALTER TABLE agent_actions ALTER COLUMN status TYPE VARCHAR(32)")
    op.execute("ALTER TABLE agent_actions ALTER COLUMN confirm_token TYPE VARCHAR(256)")

    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_actions_idempotency_key
        ON agent_actions (idempotency_key)
        WHERE idempotency_key IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_agent_actions_step
        ON agent_actions (session_id, plan_version, step_id)
        WHERE step_id IS NOT NULL
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_agent_actions_task ON agent_actions (task_id)")

    op.create_table(
        "agent_approvals",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("action_id", sa.BigInteger(), nullable=False),
        sa.Column("session_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("canvas_id", sa.BigInteger()),
        sa.Column("canvas_version", sa.Integer(), nullable=False),
        sa.Column("plan_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("tool_name", sa.String(64), nullable=False),
        sa.Column("action_hash", sa.String(64), nullable=False),
        sa.Column("estimated_cost", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chain_estimated_cost", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("approved_cost_cap", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("nonce", sa.String(64), nullable=False),
        sa.Column("token_signature", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("nonce", name="uq_agent_approvals_nonce"),
    )
    op.create_index("ix_agent_approvals_action", "agent_approvals", ["action_id"])
    op.create_index("ix_agent_approvals_session", "agent_approvals", ["session_id"])

    op.create_table(
        "agent_wakeup_notices",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("session_id", sa.BigInteger(), nullable=False),
        sa.Column("task_id", sa.String(64), nullable=False),
        sa.Column("terminal_status", sa.String(32), nullable=False),
        sa.Column("canvas_id", sa.BigInteger()),
        sa.Column("node_id", sa.BigInteger()),
        sa.Column("user_id", sa.BigInteger()),
        sa.Column("payload", sa.JSON(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("session_id", "task_id", "terminal_status", name="uq_wakeup_session_task_status"),
    )

    op.create_table(
        "render_reviews",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("canvas_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("target_node_id", sa.BigInteger(), nullable=False),
        sa.Column("target_kind", sa.String(32), server_default="clip"),
        sa.Column("scores", sa.JSON(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("failures", sa.JSON(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("recommended_action", sa.String(64)),
        sa.Column("evidence", sa.JSON(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("retry_count", sa.Integer(), server_default="0"),
        sa.Column("status", sa.String(16), server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_render_reviews_canvas_node", "render_reviews", ["canvas_id", "target_node_id"])


def downgrade() -> None:
    op.drop_index("ix_render_reviews_canvas_node", table_name="render_reviews")
    op.drop_table("render_reviews")
    op.drop_table("agent_wakeup_notices")
    op.drop_index("ix_agent_approvals_session", table_name="agent_approvals")
    op.drop_index("ix_agent_approvals_action", table_name="agent_approvals")
    op.drop_table("agent_approvals")
    op.execute("DROP INDEX IF EXISTS ix_agent_actions_task")
    op.execute("DROP INDEX IF EXISTS ix_agent_actions_step")
    op.execute("DROP INDEX IF EXISTS uq_agent_actions_idempotency_key")

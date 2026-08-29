"""track wakeup notice processing for retry-safe terminal events.

Revision ID: 002_wakeup_notice_processing
Revises: 001_control_plane
Create Date: 2026-08-27
"""

from alembic import op


revision = "002_wakeup_notice_processing"
down_revision = "001_control_plane"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE agent_wakeup_notices ADD COLUMN IF NOT EXISTS processing_at TIMESTAMPTZ")
    op.execute("ALTER TABLE agent_wakeup_notices ADD COLUMN IF NOT EXISTS processed_at TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE agent_wakeup_notices DROP COLUMN IF EXISTS processed_at")
    op.execute("ALTER TABLE agent_wakeup_notices DROP COLUMN IF EXISTS processing_at")

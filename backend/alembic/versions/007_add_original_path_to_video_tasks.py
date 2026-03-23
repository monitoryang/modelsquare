"""Add original_path column to video_tasks

Revision ID: 007
Revises: 006
Create Date: 2026-03-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = '007'
down_revision: Union[str, None] = '006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Add original_path column if it doesn't exist
    result = conn.execute(text(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'video_tasks' AND column_name = 'original_path'
        """
    ))
    if not result.fetchone():
        op.add_column('video_tasks', sa.Column('original_path', sa.String(256), nullable=True))


def downgrade() -> None:
    op.drop_column('video_tasks', 'original_path')

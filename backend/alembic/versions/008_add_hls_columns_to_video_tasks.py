"""Add hls_url and original_hls_url columns to video_tasks

Revision ID: 008
Revises: 007
Create Date: 2026-03-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = '008'
down_revision: Union[str, None] = '007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Add hls_url column if it doesn't exist
    result = conn.execute(text(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'video_tasks' AND column_name = 'hls_url'
        """
    ))
    if not result.fetchone():
        op.add_column('video_tasks', sa.Column('hls_url', sa.String(512), nullable=True))

    # Add original_hls_url column if it doesn't exist
    result = conn.execute(text(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'video_tasks' AND column_name = 'original_hls_url'
        """
    ))
    if not result.fetchone():
        op.add_column('video_tasks', sa.Column('original_hls_url', sa.String(512), nullable=True))


def downgrade() -> None:
    op.drop_column('video_tasks', 'original_hls_url')
    op.drop_column('video_tasks', 'hls_url')

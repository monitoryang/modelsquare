"""change video_size to bigint

Revision ID: 005
Revises: 004
Create Date: 2026-03-09

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '005'
down_revision: str = '004'
branch_labels = None
depends_on = None


def upgrade():
    # Change video_size and render_video_size from Integer to BigInteger
    op.alter_column('video_tasks', 'video_size',
                    existing_type=sa.Integer(),
                    type_=sa.BigInteger(),
                    existing_nullable=True)
    op.alter_column('video_tasks', 'render_video_size',
                    existing_type=sa.Integer(),
                    type_=sa.BigInteger(),
                    existing_nullable=True)


def downgrade():
    # Revert back to Integer
    op.alter_column('video_tasks', 'video_size',
                    existing_type=sa.BigInteger(),
                    type_=sa.Integer(),
                    existing_nullable=True)
    op.alter_column('video_tasks', 'render_video_size',
                    existing_type=sa.BigInteger(),
                    type_=sa.Integer(),
                    existing_nullable=True)

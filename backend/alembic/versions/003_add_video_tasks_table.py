"""Add video_tasks table

Revision ID: 003
Revises: 
Create Date: 2026-01-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum type if not exists
    conn = op.get_bind()
    
    # Check if enum type exists
    result = conn.execute(text(
        "SELECT 1 FROM pg_type WHERE typname = 'videotaskstatusdb'"
    ))
    if not result.fetchone():
        # Create the enum type
        videotaskstatusdb = postgresql.ENUM(
            'PENDING', 'PROCESSING', 'RENDERING', 'COMPLETED', 'FAILED', 'CANCELLED',
            name='videotaskstatusdb'
        )
        videotaskstatusdb.create(conn)
    
    # Check if table exists
    result = conn.execute(text(
        "SELECT 1 FROM information_schema.tables WHERE table_name = 'video_tasks'"
    ))
    if result.fetchone():
        # Table already exists, skip creation
        return
    
    # Create video_tasks table
    op.create_table(
        'video_tasks',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('task_id', sa.String(64), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('model_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('video_filename', sa.String(256), nullable=False),
        sa.Column('video_size', sa.Integer(), nullable=True),
        sa.Column('conf_threshold', sa.Float(), nullable=True, default=0.25),
        sa.Column('iou_threshold', sa.Float(), nullable=True, default=0.45),
        sa.Column('sample_fps', sa.Float(), nullable=True),
        sa.Column('background_mode', sa.Boolean(), nullable=True, default=False),
        sa.Column('status', postgresql.ENUM('PENDING', 'PROCESSING', 'RENDERING', 'COMPLETED', 'FAILED', 'CANCELLED', name='videotaskstatusdb', create_type=False), nullable=True),
        sa.Column('current_stage', sa.String(32), nullable=True),
        sa.Column('total_frames', sa.Integer(), nullable=True, default=0),
        sa.Column('processed_frames', sa.Integer(), nullable=True, default=0),
        sa.Column('progress_percent', sa.Float(), nullable=True, default=0),
        sa.Column('fps', sa.Float(), nullable=True),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('render_path', sa.String(256), nullable=True),
        sa.Column('result_path', sa.String(256), nullable=True),
        sa.Column('render_video_size', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['model_id'], ['models.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_video_tasks_status'), 'video_tasks', ['status'], unique=False)
    op.create_index(op.f('ix_video_tasks_task_id'), 'video_tasks', ['task_id'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_video_tasks_task_id'), table_name='video_tasks')
    op.drop_index(op.f('ix_video_tasks_status'), table_name='video_tasks')
    op.drop_table('video_tasks')
    # Drop enum type
    op.execute('DROP TYPE IF EXISTS videotaskstatusdb')

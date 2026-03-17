"""add OWLv2 to networktype enum

Revision ID: 006
Revises: 005
Create Date: 2026-03-16

"""
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '006'
down_revision: str = '005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE networktype ADD VALUE IF NOT EXISTS 'OWLv2'")


def downgrade() -> None:
    # PostgreSQL does not support removing values from enums easily.
    # A full migration with column recreation would be needed.
    pass

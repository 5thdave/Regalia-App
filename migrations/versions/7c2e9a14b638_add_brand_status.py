"""Add approval status to brands.

Revision ID: 7c2e9a14b638
Revises: 6f3d4bbe57b5
"""
from alembic import op
import sqlalchemy as sa


revision = '7c2e9a14b638'
down_revision = '6f3d4bbe57b5'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'brand',
        sa.Column(
            'status',
            sa.String(length=20),
            nullable=False,
            server_default='Pending',
        ),
    )


def downgrade():
    op.drop_column('brand', 'status')

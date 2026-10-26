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
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    brand_columns = {column['name'] for column in inspector.get_columns('brand')}
    if 'status' not in brand_columns:
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
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    brand_columns = {column['name'] for column in inspector.get_columns('brand')}
    if 'status' in brand_columns:
        op.drop_column('brand', 'status')

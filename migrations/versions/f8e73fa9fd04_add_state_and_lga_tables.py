"""add state and lga tables

Revision ID: f8e73fa9fd04
Revises: 48bdc103f2a1
Create Date: 2026-10-25 23:06:53.459855

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f8e73fa9fd04'
down_revision = '48bdc103f2a1'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table('state'):
        op.create_table(
            'state',
            sa.Column('state_id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('state_name', sa.String(length=80), server_default='', nullable=False),
            sa.PrimaryKeyConstraint('state_id')
        )

    inspector = sa.inspect(bind)
    if not inspector.has_table('lga'):
        op.create_table(
            'lga',
            sa.Column('lga_id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('state_id', sa.Integer(), server_default='0', nullable=False),
            sa.Column('lga_name', sa.String(length=50), server_default='', nullable=False),
            sa.ForeignKeyConstraint(['state_id'], ['state.state_id']),
            sa.PrimaryKeyConstraint('lga_id')
        )


def downgrade():
    op.drop_table('lga')
    op.drop_table('state')

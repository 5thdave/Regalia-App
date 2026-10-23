"""Add per-user favorite brands."""
from alembic import op
import sqlalchemy as sa


revision = 'c34e0bfa7162'
down_revision = 'a18c4b2d90ef'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'favorite_brands',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('brand_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['brand_id'], ['brand.brand_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', 'brand_id'),
    )


def downgrade():
    op.drop_table('favorite_brands')

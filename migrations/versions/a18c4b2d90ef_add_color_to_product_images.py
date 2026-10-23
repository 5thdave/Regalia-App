"""Associate product images with colors.

Revision ID: a18c4b2d90ef
Revises: 9e92b6dda4a0
Create Date: 2026-10-18 09:30:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'a18c4b2d90ef'
down_revision = '9e92b6dda4a0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('product_images', schema=None) as batch_op:
        batch_op.add_column(sa.Column('color_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_product_images_color_id_colors',
            'colors',
            ['color_id'],
            ['color_id'],
        )


def downgrade():
    with op.batch_alter_table('product_images', schema=None) as batch_op:
        batch_op.drop_constraint(
            'fk_product_images_color_id_colors',
            type_='foreignkey',
        )
        batch_op.drop_column('color_id')

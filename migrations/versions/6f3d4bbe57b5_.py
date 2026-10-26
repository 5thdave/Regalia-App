"""Add unique brand registration numbers and unique customer reviews.

Revision ID: 6f3d4bbe57b5
Revises: 9a7b1d3f4c20
Create Date: 2026-10-26 10:38:48.377902
"""
from alembic import op
import sqlalchemy as sa


revision = '6f3d4bbe57b5'
down_revision = '9a7b1d3f4c20'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    brand_columns = {column['name'] for column in inspector.get_columns('brand')}

    if 'brand_regno' not in brand_columns:
        op.add_column(
            'brand',
            sa.Column('brand_regno', sa.String(length=100), nullable=True),
        )
    else:
        with op.batch_alter_table(
            'brand',
            reflect_args=[sa.Column('brand_regno', sa.String(length=100), nullable=False)],
        ) as batch_op:
            batch_op.alter_column(
                'brand_regno',
                existing_type=sa.String(length=100),
                nullable=True,
            )

    op.execute(
        "UPDATE brand SET brand_regno = NULL "
        "WHERE brand_regno IS NOT NULL AND TRIM(brand_regno) = ''"
    )

    inspector = sa.inspect(bind)
    if not any(
        constraint.get('column_names') == ['brand_regno']
        for constraint in inspector.get_unique_constraints('brand')
    ):
        with op.batch_alter_table('brand') as batch_op:
            batch_op.create_unique_constraint(
                'uq_brand_brand_regno',
                ['brand_regno'],
            )

    inspector = sa.inspect(bind)
    if not any(
        constraint.get('column_names') == ['user_id', 'product_id']
        for constraint in inspector.get_unique_constraints('review')
    ):
        with op.batch_alter_table('review') as batch_op:
            batch_op.create_unique_constraint(
                'uq_review_user_product',
                ['user_id', 'product_id'],
            )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    review_constraints = inspector.get_unique_constraints('review')
    if any(
        constraint.get('column_names') == ['user_id', 'product_id']
        for constraint in review_constraints
    ):
        with op.batch_alter_table('review') as batch_op:
            batch_op.drop_constraint('uq_review_user_product', type_='unique')

    inspector = sa.inspect(bind)
    brand_columns = {column['name'] for column in inspector.get_columns('brand')}
    brand_constraints = inspector.get_unique_constraints('brand')
    if 'brand_regno' in brand_columns:
        with op.batch_alter_table('brand') as batch_op:
            for constraint in brand_constraints:
                if constraint.get('column_names') == ['brand_regno']:
                    batch_op.drop_constraint(constraint['name'], type_='unique')
            batch_op.drop_column('brand_regno')

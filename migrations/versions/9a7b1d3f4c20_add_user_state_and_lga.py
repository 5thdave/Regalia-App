"""Add state and local government selection to users.

Revision ID: 9a7b1d3f4c20
Revises: f8e73fa9fd04
"""
from alembic import op
import sqlalchemy as sa


revision = '9a7b1d3f4c20'
down_revision = 'f8e73fa9fd04'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    user_columns = {column['name'] for column in inspector.get_columns('users')}
    foreign_keys = inspector.get_foreign_keys('users')

    with op.batch_alter_table('users') as batch_op:
        if 'state_id' not in user_columns:
            batch_op.add_column(sa.Column('state_id', sa.Integer(), nullable=True))
        if 'lga_id' not in user_columns:
            batch_op.add_column(sa.Column('lga_id', sa.Integer(), nullable=True))
        if not any(
            fk['constrained_columns'] == ['state_id'] and fk['referred_table'] == 'state'
            for fk in foreign_keys
        ):
            batch_op.create_foreign_key(
                'fk_users_state_id_state',
                'state',
                ['state_id'],
                ['state_id'],
            )
        if not any(
            fk['constrained_columns'] == ['lga_id'] and fk['referred_table'] == 'lga'
            for fk in foreign_keys
        ):
            batch_op.create_foreign_key(
                'fk_users_lga_id_lga',
                'lga',
                ['lga_id'],
                ['lga_id'],
            )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    user_columns = {column['name'] for column in inspector.get_columns('users')}
    foreign_keys = inspector.get_foreign_keys('users')

    with op.batch_alter_table('users') as batch_op:
        for fk in foreign_keys:
            if fk['name'] and fk['constrained_columns'] in (['state_id'], ['lga_id']):
                batch_op.drop_constraint(fk['name'], type_='foreignkey')
        if 'lga_id' in user_columns:
            batch_op.drop_column('lga_id')
        if 'state_id' in user_columns:
            batch_op.drop_column('state_id')

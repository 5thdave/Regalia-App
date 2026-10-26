"""Add newsletter subscribers.

Revision ID: 6f2a9c1d4b70
Revises: c34e0bfa7162
Create Date: 2026-10-24 01:45:00
"""
from alembic import op
import sqlalchemy as sa


revision = '6f2a9c1d4b70'
down_revision = 'c34e0bfa7162'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table('newsletter_subscribers'):
        op.create_table(
            'newsletter_subscribers',
            sa.Column('subscriber_id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('email', sa.String(length=254), nullable=False),
            sa.Column(
                'subscribed_at',
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint('subscriber_id'),
        )
        op.create_index(
            'ix_newsletter_subscribers_email',
            'newsletter_subscribers',
            ['email'],
            unique=True,
        )
    else:
        indexes = {ix['name'] for ix in inspector.get_indexes('newsletter_subscribers')}
        if 'ix_newsletter_subscribers_email' not in indexes:
            op.create_index(
                'ix_newsletter_subscribers_email',
                'newsletter_subscribers',
                ['email'],
                unique=True,
            )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table('newsletter_subscribers'):
        indexes = {ix['name'] for ix in inspector.get_indexes('newsletter_subscribers')}
        if 'ix_newsletter_subscribers_email' in indexes:
            op.drop_index(
                'ix_newsletter_subscribers_email',
                table_name='newsletter_subscribers',
            )
        op.drop_table('newsletter_subscribers')

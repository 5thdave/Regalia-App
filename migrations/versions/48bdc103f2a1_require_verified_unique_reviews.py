"""Require purchase verification and one review per customer and product.

Revision ID: 48bdc103f2a1
Revises: 6f2a9c1d4b70
Create Date: 2026-10-24 02:04:00
"""
from alembic import op


revision = '48bdc103f2a1'
down_revision = '6f2a9c1d4b70'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        UPDATE review
        SET order_item_id = (
            SELECT oi.orderitem_id
            FROM order_items AS oi
            JOIN orders AS o ON o.order_id = oi.itemorder_id
            JOIN payment AS p ON p.paymentorder_id = o.order_id
            WHERE o.orderuser_id = review.user_id
              AND oi.itemproduct_id = review.product_id
              AND p.status = 'Completed'
              AND (o.order_status IS NULL OR o.order_status != 'Cancelled')
            ORDER BY o.order_date DESC, oi.orderitem_id DESC
            LIMIT 1
        )
        WHERE order_item_id IS NULL
          AND EXISTS (
              SELECT 1
              FROM order_items AS oi
              JOIN orders AS o ON o.order_id = oi.itemorder_id
              JOIN payment AS p ON p.paymentorder_id = o.order_id
              WHERE o.orderuser_id = review.user_id
                AND oi.itemproduct_id = review.product_id
                AND p.status = 'Completed'
                AND (o.order_status IS NULL OR o.order_status != 'Cancelled')
          )
        """
    )
    op.execute(
        """
        DELETE FROM review
        WHERE NOT EXISTS (
            SELECT 1
            FROM order_items AS oi
            JOIN orders AS o ON o.order_id = oi.itemorder_id
            JOIN payment AS p ON p.paymentorder_id = o.order_id
            WHERE oi.orderitem_id = review.order_item_id
              AND o.orderuser_id = review.user_id
              AND oi.itemproduct_id = review.product_id
              AND p.status = 'Completed'
              AND (o.order_status IS NULL OR o.order_status != 'Cancelled')
        )
        """
    )
    op.execute(
        """
        DELETE FROM review
        WHERE review_id NOT IN (
            SELECT review_id
            FROM (
                SELECT MIN(review_id) AS review_id
                FROM review
                GROUP BY user_id, product_id
            ) AS retained_reviews
        )
        """
    )
    with op.batch_alter_table('review') as batch_op:
        batch_op.create_unique_constraint(
            'uq_review_user_product',
            ['user_id', 'product_id'],
        )


def downgrade():
    with op.batch_alter_table('review') as batch_op:
        batch_op.drop_constraint('uq_review_user_product', type_='unique')

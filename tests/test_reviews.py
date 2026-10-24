import os
import unittest
from decimal import Decimal
from sqlalchemy.exc import IntegrityError

os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['SECRET_KEY'] = 'review-test-key'

from pkg import app
from pkg.models import (
    Brand,
    Category,
    Order,
    OrderItem,
    Payment,
    Product,
    Review,
    User,
    db,
)


class ProductReviewTestCase(unittest.TestCase):
    def setUp(self):
        app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            SECRET_KEY='review-test-key',
        )
        self.app_context = app.app_context()
        self.app_context.push()
        db.drop_all()
        db.create_all()
        self.client = app.test_client()

        self.customer = User(
            name='Verified Shopper',
            email='shopper@example.com',
            status='Active',
        )
        self.brand = Brand(brand_name='Review Brand', brand_email='review-brand@example.com')
        category = Category(category_name='Clothing')
        db.session.add_all([self.customer, self.brand, category])
        db.session.flush()
        self.product = Product(
            product_name='Reviewable Product',
            brand_id=self.brand.brand_id,
            category_id=category.category_id,
            price=Decimal('50.00'),
            status='Available',
        )
        db.session.add(self.product)
        db.session.commit()

        self.user_id = self.customer.id
        self.product_id = self.product.product_id
        self.brand_id = self.brand.brand_id
        with self.client.session_transaction() as session:
            session['useronline'] = self.user_id

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.app_context.pop()

    def create_completed_purchase(self, user_id=None):
        user_id = user_id or self.user_id
        order = Order(
            orderuser_id=user_id,
            order_amt=Decimal('50.00'),
            order_status='Processing',
        )
        db.session.add(order)
        db.session.flush()
        order_item = OrderItem(
            itemorder_id=order.order_id,
            itemproduct_id=self.product_id,
            quantity=1,
            unit_price=Decimal('50.00'),
        )
        payment = Payment(
            paymentorder_id=order.order_id,
            paymentuser_id=user_id,
            payment_method='Paystack',
            transaction_ref=f'REVIEW-ORDER-{order.order_id}',
            amount=Decimal('50.00'),
            currency='NGN',
            status='Completed',
            payment_gateway='Paystack',
        )
        db.session.add_all([order_item, payment])
        db.session.commit()
        return order_item

    def submit_review(self, rating='5', comment=''):
        return self.client.post(
            f'/user/reviews/{self.product_id}',
            data={'rating': rating, 'comment': comment},
        )

    def test_review_requires_completed_purchase_and_links_order_item(self):
        response = self.submit_review(rating='4', comment='Comfortable and well made')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Review.query.count(), 0)

        purchased_item = self.create_completed_purchase()
        response = self.submit_review(rating='4', comment='Comfortable and well made')

        self.assertEqual(response.status_code, 302)
        review = Review.query.one()
        self.assertEqual(review.user_id, self.user_id)
        self.assertEqual(review.product_id, self.product_id)
        self.assertEqual(review.order_item_id, purchased_item.orderitem_id)
        self.assertEqual(review.rating, 4)

    def test_cancelled_order_and_incomplete_payment_do_not_qualify(self):
        order = Order(
            orderuser_id=self.user_id,
            order_amt=Decimal('50.00'),
            order_status='Cancelled',
        )
        db.session.add(order)
        db.session.flush()
        db.session.add_all([
            OrderItem(
                itemorder_id=order.order_id,
                itemproduct_id=self.product_id,
                quantity=1,
                unit_price=Decimal('50.00'),
            ),
            Payment(
                paymentorder_id=order.order_id,
                paymentuser_id=self.user_id,
                payment_method='Paystack',
                transaction_ref='CANCELLED-REVIEW-ORDER',
                amount=Decimal('50.00'),
                currency='NGN',
                status='Completed',
                payment_gateway='Paystack',
            ),
        ])
        db.session.commit()

        self.submit_review()
        self.assertEqual(Review.query.count(), 0)

        db.session.query(Order).filter_by(order_id=order.order_id).update(
            {Order.order_status: 'Processing'}
        )
        db.session.query(Payment).filter_by(
            paymentorder_id=order.order_id
        ).update({Payment.status: 'Pending'})
        db.session.commit()

        self.submit_review()
        self.assertEqual(Review.query.count(), 0)

    def test_customer_can_review_product_only_once(self):
        self.create_completed_purchase()
        self.submit_review(rating='4', comment='First review')
        second_response = self.submit_review(rating='2', comment='Second review')

        self.assertEqual(second_response.status_code, 302)
        self.assertEqual(Review.query.filter_by(user_id=self.user_id).count(), 1)
        self.assertEqual(Review.query.one().comment, 'First review')

    def test_database_constraint_prevents_duplicate_customer_product_reviews(self):
        purchased_item = self.create_completed_purchase()
        db.session.add(Review(
            user_id=self.user_id,
            product_id=self.product_id,
            order_item_id=purchased_item.orderitem_id,
            rating=4,
        ))
        db.session.commit()
        db.session.add(Review(
            user_id=self.user_id,
            product_id=self.product_id,
            order_item_id=purchased_item.orderitem_id,
            rating=5,
        ))

        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()
        self.assertEqual(Review.query.filter_by(user_id=self.user_id).count(), 1)

    def test_product_page_shows_average_rating_and_customer_reviews(self):
        purchased_item = self.create_completed_purchase()
        db.session.add(Review(
            user_id=self.user_id,
            product_id=self.product_id,
            order_item_id=purchased_item.orderitem_id,
            rating=4,
            comment='Comfortable and well made',
        ))
        second_customer = User(
            name='Another Shopper',
            email='another@example.com',
            status='Active',
        )
        db.session.add(second_customer)
        db.session.flush()
        second_item = self.create_completed_purchase(second_customer.id)
        db.session.add(Review(
            user_id=second_customer.id,
            product_id=self.product_id,
            order_item_id=second_item.orderitem_id,
            rating=2,
            comment='Sizing was smaller than expected',
        ))
        db.session.commit()

        response = self.client.get(f'/shopcollection/{self.brand_id}')

        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn('3.0 out of 5 from 2 reviews', page)
        self.assertIn('Customer reviews', page)
        self.assertIn('Comfortable and well made', page)
        self.assertIn('Sizing was smaller than expected', page)
        self.assertIn('Verified Shopper', page)

    def test_customer_without_purchase_sees_review_requirement(self):
        response = self.client.get(f'/shopcollection/{self.brand_id}')

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            'Purchase to write a review',
            response.get_data(as_text=True),
        )


if __name__ == '__main__':
    unittest.main()

import os
import unittest
from decimal import Decimal
from unittest.mock import Mock, patch

os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['SECRET_KEY'] = 'payment-inventory-test-key'

from pkg import app
from pkg.models import Brand, Order, OrderItem, Payment, Product, ProductVariant, User, db


class PaymentInventoryTestCase(unittest.TestCase):
    def setUp(self):
        app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            SECRET_KEY='payment-inventory-test-key',
        )
        self.app_context = app.app_context()
        self.app_context.push()
        db.drop_all()
        db.create_all()
        self.client = app.test_client()

        customer = User(
            name='Test Customer',
            email='customer@example.com',
            status='Active',
        )
        brand = Brand(brand_name='Test Brand', brand_email='brand@example.com')
        db.session.add_all([customer, brand])
        db.session.flush()

        product = Product(
            product_name='Test Shirt',
            brand_id=brand.brand_id,
            price=Decimal('25.00'),
            status='Available',
        )
        db.session.add(product)
        db.session.flush()

        variant = ProductVariant(
            productvariant_id=product.product_id,
            stock_quantity=5,
            price=Decimal('25.00'),
        )
        db.session.add(variant)
        db.session.flush()

        order = Order(
            orderuser_id=customer.id,
            order_amt=Decimal('50.00'),
            order_status='Pending',
        )
        db.session.add(order)
        db.session.flush()

        payment = Payment(
            paymentorder_id=order.order_id,
            paymentuser_id=customer.id,
            payment_method='Paystack',
            transaction_ref='ORDER-INVENTORY-TEST',
            amount=Decimal('50.00'),
            currency='NGN',
            status='Pending',
            payment_gateway='Paystack',
        )
        db.session.add_all([
            OrderItem(
                itemorder_id=order.order_id,
                itemproduct_id=product.product_id,
                itemvariant_id=variant.variant_id,
                quantity=1,
                unit_price=Decimal('25.00'),
            ),
            OrderItem(
                itemorder_id=order.order_id,
                itemproduct_id=product.product_id,
                itemvariant_id=variant.variant_id,
                quantity=1,
                unit_price=Decimal('25.00'),
            ),
            payment,
        ])
        db.session.commit()

        self.order_id = order.order_id
        self.payment_id = payment.payment_id
        self.variant_id = variant.variant_id
        self.initial_stock = variant.stock_quantity
        app.config['PAYSTACK_API_SECRET_KEY'] = 'test-paystack-secret'

        with self.client.session_transaction() as session:
            session['useronline'] = customer.id

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.app_context.pop()

    def verify_payment(self, status='success'):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            'status': True,
            'data': {
                'reference': 'ORDER-INVENTORY-TEST',
                'amount': 5000,
                'currency': 'NGN',
                'status': status,
            },
        }
        return response

    @patch('pkg.user.routes.requests.get')
    def test_successful_payment_decrements_ordered_stock(self, get_payment):
        get_payment.return_value = self.verify_payment()

        response = self.client.get('/user/pay/confirm/?reference=ORDER-INVENTORY-TEST')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            db.session.get(ProductVariant, self.variant_id).stock_quantity,
            self.initial_stock - 2,
        )
        self.assertEqual(db.session.get(Payment, self.payment_id).status, 'Completed')
        self.assertEqual(db.session.get(Order, self.order_id).order_status, 'Processing')
        self.assertEqual(
            get_payment.call_args.kwargs['headers']['Authorization'],
            'Bearer test-paystack-secret',
        )

    @patch('pkg.user.routes.requests.get')
    def test_repeated_success_callback_does_not_decrement_stock_twice(self, get_payment):
        get_payment.return_value = self.verify_payment()
        callback_url = '/user/pay/confirm/?reference=ORDER-INVENTORY-TEST'

        self.client.get(callback_url)
        self.client.get(callback_url)

        self.assertEqual(
            db.session.get(ProductVariant, self.variant_id).stock_quantity,
            self.initial_stock - 2,
        )
        self.assertEqual(get_payment.call_count, 2)

    @patch('pkg.user.routes.requests.get')
    def test_successful_payment_with_insufficient_stock_keeps_stock_and_flags_order(
        self,
        get_payment,
    ):
        get_payment.return_value = self.verify_payment()
        variant = db.session.get(ProductVariant, self.variant_id)
        variant.stock_quantity = 1
        db.session.commit()

        response = self.client.get('/user/pay/confirm/?reference=ORDER-INVENTORY-TEST')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(db.session.get(ProductVariant, self.variant_id).stock_quantity, 1)
        self.assertEqual(db.session.get(Payment, self.payment_id).status, 'Completed')
        self.assertEqual(db.session.get(Order, self.order_id).order_status, 'Cancelled')

    @patch('pkg.user.routes.requests.get')
    def test_insufficient_later_variant_rolls_back_earlier_stock_updates(
        self,
        get_payment,
    ):
        get_payment.return_value = self.verify_payment()
        product = db.session.get(ProductVariant, self.variant_id).product
        unavailable_variant = ProductVariant(
            productvariant_id=product.product_id,
            stock_quantity=1,
            price=Decimal('25.00'),
        )
        db.session.add(unavailable_variant)
        db.session.flush()
        db.session.add(
            OrderItem(
                itemorder_id=self.order_id,
                itemproduct_id=product.product_id,
                itemvariant_id=unavailable_variant.variant_id,
                quantity=2,
                unit_price=Decimal('25.00'),
            )
        )
        db.session.commit()
        unavailable_variant_id = unavailable_variant.variant_id

        self.client.get('/user/pay/confirm/?reference=ORDER-INVENTORY-TEST')

        self.assertEqual(
            db.session.get(ProductVariant, self.variant_id).stock_quantity,
            self.initial_stock,
        )
        self.assertEqual(
            db.session.get(ProductVariant, unavailable_variant_id).stock_quantity,
            1,
        )
        self.assertEqual(db.session.get(Payment, self.payment_id).status, 'Completed')
        self.assertEqual(db.session.get(Order, self.order_id).order_status, 'Cancelled')

    @patch('pkg.user.routes.requests.get')
    def test_failed_payment_does_not_decrement_stock(self, get_payment):
        get_payment.return_value = self.verify_payment(status='failed')

        response = self.client.get('/user/pay/confirm/?reference=ORDER-INVENTORY-TEST')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            db.session.get(ProductVariant, self.variant_id).stock_quantity,
            self.initial_stock,
        )
        self.assertEqual(db.session.get(Payment, self.payment_id).status, 'Failed')
        self.assertEqual(db.session.get(Order, self.order_id).order_status, 'Cancelled')


if __name__ == '__main__':
    unittest.main()

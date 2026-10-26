import os
import unittest

os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['SECRET_KEY'] = 'shop-test-key'

from pkg import app
from pkg.models import Brand, BrandLogo, db


class ShopPageTestCase(unittest.TestCase):
    def setUp(self):
        app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            SECRET_KEY='shop-test-key',
        )
        self.app_context = app.app_context()
        self.app_context.push()
        db.drop_all()
        db.create_all()
        brand = Brand(
            brand_regno='CAC-SHOP-123',
            brand_name='Test Shop Brand',
            brand_email='shop-brand@example.com',
            status='Approved',
        )
        db.session.add(brand)
        db.session.flush()
        db.session.add(BrandLogo(brand_id=brand.brand_id, logo='test-logo.png'))
        db.session.commit()
        self.brand = brand
        self.client = app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.app_context.pop()

    def test_shop_renders_brand_logo_and_collection_link(self):
        response = self.client.get('/shop')

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            f'href="/shopcollection/{self.brand.brand_id}"'.encode(),
            response.data,
        )
        self.assertIn(
            b'/static/media/brandlogos/test-logo.png',
            response.data,
        )
        self.assertIn(b'Test Shop Brand Logo', response.data)


if __name__ == '__main__':
    unittest.main()

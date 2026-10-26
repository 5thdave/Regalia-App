import os
import unittest
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['SECRET_KEY'] = 'vendor-upload-test-key'

from pkg import app
from pkg.models import Brand, BrandLogo, Category, Color, Product, ProductImage, ProductVariant, Size, db
from sqlalchemy.exc import SQLAlchemyError


class VendorUploadTestCase(unittest.TestCase):
    def setUp(self):
        app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            SECRET_KEY='vendor-upload-test-key',
        )
        self.app_context = app.app_context()
        self.app_context.push()
        db.drop_all()
        db.create_all()
        self.client = app.test_client()

        brand = Brand(
            brand_name='Test Brand',
            brand_email='vendor@example.com',
            status='Approved',
        )
        category = Category(category_name='Clothing')
        color = Color(color_name='Test Blue', hex_code='#123456')
        size = Size(size_code='M', size_name='Medium')
        db.session.add_all([brand, category, color, size])
        db.session.commit()

        self.brand_id = brand.brand_id
        self.category_id = category.category_id
        self.color_id = color.color_id
        self.size_id = size.size_id
        with self.client.session_transaction() as session:
            session['brandonline'] = self.brand_id

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.app_context.pop()

    def upload_form(self, **overrides):
        data = {
            'product_name': 'Test Product',
            'category': str(self.category_id),
            'base_price': '125.50',
            'description': 'A test product',
            'status': 'Available',
            'variant_color[]': [str(self.color_id)],
            'variant_size[]': [str(self.size_id)],
            'variant_price[]': [''],
            'variant_stock[]': ['4'],
        }
        data.update(overrides)
        return data

    def post_upload(self, data):
        return self.client.post(
            '/vendor/upload',
            data=data,
            content_type='multipart/form-data',
        )

    def test_unapproved_brand_cannot_view_or_submit_product_upload(self):
        brand = db.session.get(Brand, self.brand_id)
        brand.status = 'Pending'
        db.session.commit()

        get_response = self.client.get('/vendor/upload')
        post_response = self.post_upload(self.upload_form())

        self.assertEqual(get_response.status_code, 302)
        self.assertEqual(post_response.status_code, 302)
        self.assertEqual(Product.query.count(), 0)
        with self.client.session_transaction() as session:
            self.assertEqual(session['_flashes'][-1][1],
                             'Your brand must be approved before you can upload products.')

    def test_vendor_profile_displays_basic_brand_details(self):
        brand = db.session.get(Brand, self.brand_id)
        brand.brand_regno = 'CAC-12345'
        brand.brand_phone = '08012345678'
        brand.brand_desc = 'Locally made fashion'
        db.session.add(BrandLogo(brand_id=self.brand_id, logo='test-logo.png'))
        db.session.commit()

        response = self.client.get('/vendor/profile')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Test Brand', response.data)
        self.assertIn(b'vendor@example.com', response.data)
        self.assertIn(b'08012345678', response.data)
        self.assertIn(b'CAC-12345', response.data)
        self.assertIn(b'Locally made fashion', response.data)
        self.assertIn(b'Approved', response.data)
        self.assertIn(b'/static/media/brandlogos/test-logo.png', response.data)

    def test_vendor_profile_clears_stale_brand_session(self):
        with self.client.session_transaction() as session:
            session['brandonline'] = 99999

        response = self.client.get('/vendor/profile')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], '/login')
        with self.client.session_transaction() as session:
            self.assertNotIn('brandonline', session)

    def test_valid_upload_saves_product_variant_and_png(self):
        response = self.post_upload(self.upload_form(
            product_images=(BytesIO(b'\x89PNG\r\n\x1a\nfake-image-data'), 'item.png'),
            **{'product_image_colors[]': [str(self.color_id)]},
        ))

        self.assertEqual(response.status_code, 302)
        product = Product.query.one()
        variant = ProductVariant.query.one()
        image = ProductImage.query.one()
        self.assertEqual(product.category_id, self.category_id)
        self.assertEqual(product.price, Decimal('125.50'))
        self.assertEqual(product.status, 'Available')
        self.assertEqual(variant.color_id, self.color_id)
        self.assertEqual(variant.size_id, self.size_id)
        self.assertEqual(variant.price, Decimal('125.50'))
        self.assertEqual(variant.stock_quantity, 4)
        self.assertEqual(image.color_id, self.color_id)
        stored_path = os.path.join(app.root_path, 'static', 'media', image.image)
        self.assertTrue(os.path.isfile(stored_path))
        os.remove(stored_path)

    def test_invalid_product_fields_are_rejected_without_database_records(self):
        invalid_forms = [
            ('invalid base price', {'base_price': '-1'}),
            ('excessive base price', {'base_price': '100000000'}),
            ('unknown category', {'category': '999999'}),
            ('unknown status', {'status': 'Published'}),
            ('unknown variant color', {'variant_color[]': ['999999']}),
            ('unknown variant size', {'variant_size[]': ['999999']}),
            ('negative stock', {'variant_stock[]': ['-2']}),
            ('fractional stock', {'variant_stock[]': ['1.5']}),
            ('invalid variant price', {'variant_price[]': ['0']}),
        ]

        for label, overrides in invalid_forms:
            with self.subTest(label=label):
                response = self.post_upload(self.upload_form(**overrides))
                self.assertEqual(response.status_code, 400)
                self.assertEqual(Product.query.count(), 0)

    def test_duplicate_variant_combinations_are_rejected(self):
        data = self.upload_form(
            **{
                'variant_color[]': [str(self.color_id), str(self.color_id)],
                'variant_size[]': [str(self.size_id), str(self.size_id)],
                'variant_price[]': ['', ''],
                'variant_stock[]': ['1', '2'],
            }
        )

        response = self.post_upload(data)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Product.query.count(), 0)

    def test_non_image_file_and_image_over_size_limit_are_rejected(self):
        invalid_type = self.post_upload(self.upload_form(
            product_images=(BytesIO(b'not an image'), 'item.png'),
        ))
        self.assertEqual(invalid_type.status_code, 400)
        self.assertEqual(Product.query.count(), 0)

        oversized_image = self.post_upload(self.upload_form(
            product_images=(
                BytesIO(b'\x89PNG\r\n\x1a\n' + b'x' * (5 * 1024 * 1024)),
                'large.png',
            ),
        ))
        self.assertEqual(oversized_image.status_code, 400)
        self.assertEqual(Product.query.count(), 0)

    @patch('pkg.vendor.routes.secrets.token_hex', return_value='vendoruploadtest')
    @patch('pkg.vendor.routes.db.session.commit', side_effect=SQLAlchemyError('database failure'))
    def test_database_failure_removes_uploaded_image(self, commit, token_hex):
        uploaded_path = os.path.join(
            app.root_path,
            'static',
            'media',
            'vendoruploadtest_item.png',
        )
        if os.path.exists(uploaded_path):
            os.remove(uploaded_path)

        response = self.post_upload(self.upload_form(
            product_images=(BytesIO(b'\x89PNG\r\n\x1a\nfake-image-data'), 'item.png'),
        ))

        self.assertEqual(response.status_code, 503)
        self.assertFalse(os.path.exists(uploaded_path))
        self.assertEqual(Product.query.count(), 0)
        self.assertEqual(commit.call_count, 1)
        self.assertEqual(token_hex.call_count, 1)


if __name__ == '__main__':
    unittest.main()

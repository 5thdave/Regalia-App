import os
import tempfile
import unittest
from io import BytesIO
from unittest.mock import patch

os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['SECRET_KEY'] = 'vendor-registration-test-key'

from pkg import app
from pkg.models import Brand, BrandLogo, db


class VendorRegistrationTestCase(unittest.TestCase):
    def setUp(self):
        app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            SECRET_KEY='vendor-registration-test-key',
            MAIL_USERNAME='signup@example.com',
            MAIL_PASSWORD='test-mail-password',
            MAIL_DEFAULT_SENDER='signup@example.com',
        )
        self.original_root_path = app.root_path
        self.temp_dir = tempfile.TemporaryDirectory()
        app.root_path = self.temp_dir.name
        self.app_context = app.app_context()
        self.app_context.push()
        db.drop_all()
        db.create_all()
        self.client = app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.app_context.pop()
        app.root_path = self.original_root_path
        self.temp_dir.cleanup()

    def test_registration_sends_welcome_email_to_brand_contact(self):
        with patch('pkg.vendor.routes.mail.send') as send_mail:
            response = self.client.post(
                '/vendor/register',
                data={
                    'regno': 'CAC-12345',
                    'name': 'Test Brand',
                    'email': 'BRAND@example.com',
                    'phone': '08012345678',
                    'password': 'secure-pass',
                    'confirmpassword': 'secure-pass',
                    'description': 'A test brand',
                    'brand_logo': (BytesIO(b'logo data'), 'brand.png'),
                },
                content_type='multipart/form-data',
            )

        self.assertEqual(response.status_code, 302)
        brand = Brand.query.one()
        self.assertEqual(brand.brand_name, 'Test Brand')
        self.assertEqual(brand.brand_email, 'brand@example.com')
        self.assertEqual(BrandLogo.query.count(), 1)
        send_mail.assert_called_once()
        message = send_mail.call_args.args[0]
        self.assertEqual(message.recipients, ['brand@example.com'])
        self.assertEqual(message.subject, 'Welcome to Regalia')
        self.assertIn('Test Brand', message.body)
        self.assertIn('Test Brand', message.html)

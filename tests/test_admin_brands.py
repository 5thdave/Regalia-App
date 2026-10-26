import os
import unittest
from unittest.mock import patch

os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['SECRET_KEY'] = 'admin-brands-test-key'

from pkg import app
from pkg.models import Admin, Brand, db


class AdminBrandManagementTestCase(unittest.TestCase):
    def setUp(self):
        app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            SECRET_KEY='admin-brands-test-key',
        )
        self.app_context = app.app_context()
        self.app_context.push()
        db.drop_all()
        db.create_all()
        admin_user = Admin(
            name='Test Admin',
            email='admin@example.com',
            password='test-password',
        )
        self.brand = Brand(
            brand_regno='CAC-123',
            brand_name='Test Brand',
            brand_email='brand@example.com',
            brand_phone='08012345678',
            brand_desc='A test fashion brand',
        )
        db.session.add_all([admin_user, self.brand])
        db.session.commit()
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session['admin_id'] = admin_user.id
            session['role'] = 'admin'

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.app_context.pop()

    def test_brands_page_renders_details_modal_with_status_form(self):
        response = self.client.get('/admin/brands')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Test Brand', response.data)
        self.assertIn(b'brand-modal-', response.data)
        self.assertIn(b'A test fashion brand', response.data)
        self.assertIn(b'name="status"', response.data)
        self.assertIn(b'Approved', response.data)

    def test_admin_can_update_brand_status(self):
        with patch('pkg.admin.routes.mail.send') as send_mail:
            response = self.client.post(
                f'/admin/brands/{self.brand.brand_id}/status',
                data={'status': 'Approved'},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            db.session.get(Brand, self.brand.brand_id).status,
            'Approved',
        )
        send_mail.assert_called_once()

    def test_rejecting_brand_updates_status_without_deleting_it(self):
        with patch('pkg.admin.routes.mail.send') as send_mail:
            response = self.client.post(
                f'/admin/brands/{self.brand.brand_id}/status',
                data={'status': 'Rejected'},
            )

        self.assertEqual(response.status_code, 302)
        brand = db.session.get(Brand, self.brand.brand_id)
        self.assertIsNotNone(brand)
        self.assertEqual(brand.status, 'Rejected')
        send_mail.assert_called_once()

    def test_pending_status_does_not_try_to_send_unassigned_message(self):
        with patch('pkg.admin.routes.mail.send') as send_mail:
            response = self.client.post(
                f'/admin/brands/{self.brand.brand_id}/status',
                data={'status': 'Pending'},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            db.session.get(Brand, self.brand.brand_id).status,
            'Pending',
        )
        send_mail.assert_not_called()

    def test_invalid_brand_status_is_not_saved(self):
        response = self.client.post(
            f'/admin/brands/{self.brand.brand_id}/status',
            data={'status': 'Unknown'},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            db.session.get(Brand, self.brand.brand_id).status,
            'Pending',
        )

import os
import unittest
from unittest.mock import patch

os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['SECRET_KEY'] = 'signup-test-key'

from pkg import app
from pkg.models import Lga, State, User, db
from werkzeug.security import check_password_hash


class UserSignupTestCase(unittest.TestCase):
    def setUp(self):
        app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            SECRET_KEY='signup-test-key',
            MAIL_USERNAME='signup@example.com',
            MAIL_PASSWORD='test-mail-password',
            MAIL_DEFAULT_SENDER='signup@example.com',
        )
        self.app_context = app.app_context()
        self.app_context.push()
        db.drop_all()
        db.create_all()
        self.state = State(state_name='Lagos')
        db.session.add(self.state)
        db.session.flush()
        self.lga = Lga(state_id=self.state.state_id, lga_name='Ikeja')
        db.session.add(self.lga)
        db.session.commit()
        self.client = app.test_client()

    def test_signup_form_offers_available_states(self):
        response = self.client.get('/signup')

        self.assertEqual(response.status_code, 200)
        self.assertIn(f'value="{self.state.state_id}"'.encode(), response.data)
        self.assertIn(b'Lagos</option>', response.data)

    def test_login_form_selects_brand_tab_from_query_parameter(self):
        response = self.client.get('/login?type=brand')

        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertRegex(page, r'id="brandTabBtn"[^>]*aria-selected="true"')
        self.assertRegex(page, r'id="userLoginForm"[^>]*hidden')

    def test_failed_brand_login_keeps_brand_tab_selected(self):
        response = self.client.post('/login', data={
            'login_type': 'brand',
            'email': 'brand@example.com',
            'password': 'wrong-password',
        })

        self.assertEqual(response.status_code, 200)
        self.assertRegex(
            response.get_data(as_text=True),
            r'id="brandTabBtn"[^>]*aria-selected="true"',
        )
        self.assertIn(b'Invalid email or password.', response.data)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.app_context.pop()

    def test_signup_saves_user_and_sends_confirmation_email(self):
        with patch('pkg.main.routes.mail.send') as send_mail:
            response = self.client.post('/signup', data={
                'username': 'Test Shopper',
                'email': ' Shopper@Example.com ',
                'gender': 'Female',
                'dob': '2000-01-02',
                'phone': '12345678',
                'state_id': str(self.state.state_id),
                'lga_id': str(self.lga.lga_id),
                'address': 'Test address',
                'password': 'secure-pass',
                'confirmpassword': 'secure-pass',
            })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], '/login')
        user = User.query.one()
        self.assertEqual(user.email, 'shopper@example.com')
        self.assertEqual(user.gender, 'Female')
        self.assertEqual(user.dateofbirth.isoformat(), '2000-01-02')
        self.assertEqual(user.state_id, self.state.state_id)
        self.assertEqual(user.lga_id, self.lga.lga_id)
        self.assertTrue(check_password_hash(user.password, 'secure-pass'))
        send_mail.assert_called_once()
        message = send_mail.call_args.args[0]
        self.assertEqual(message.recipients, ['shopper@example.com'])
        self.assertEqual(message.subject, 'Welcome to Regalia')

    def test_signup_reports_missing_mail_configuration(self):
        app.config['MAIL_PASSWORD'] = None

        response = self.client.post('/signup', data={
            'username': 'Test Shopper',
            'email': 'shopper@example.com',
            'gender': 'Female',
            'dob': '2000-01-02',
            'phone': '12345678',
            'state_id': str(self.state.state_id),
            'lga_id': str(self.lga.lga_id),
            'password': 'secure-pass',
            'confirmpassword': 'secure-pass',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(User.query.count(), 1)
        self.assertIn(b'email delivery is not configured', self.client.get('/login').data)

    def test_signup_rejects_duplicate_email(self):
        db.session.add(User(email='shopper@example.com'))
        db.session.commit()

        response = self.client.post('/signup', data={
            'username': 'Test Shopper',
            'email': 'SHOPPER@example.com',
            'gender': 'Female',
            'dob': '2000-01-02',
            'phone': '12345678',
            'state_id': str(self.state.state_id),
            'lga_id': str(self.lga.lga_id),
            'password': 'secure-pass',
            'confirmpassword': 'secure-pass',
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.query.count(), 1)
        self.assertIn(b'already exists', response.data)

    def test_signup_rejects_invalid_date_and_mismatched_passwords(self):
        form_data = {
            'username': 'Test Shopper',
            'email': 'shopper@example.com',
            'gender': 'Male',
            'dob': 'not-a-date',
            'phone': '12345678',
            'state_id': str(self.state.state_id),
            'lga_id': str(self.lga.lga_id),
            'password': 'secure-pass',
            'confirmpassword': 'secure-pass',
        }

        response = self.client.post('/signup', data=form_data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.query.count(), 0)
        self.assertIn(b'valid date of birth', response.data)

        form_data['dob'] = '2000-01-02'
        form_data['confirmpassword'] = 'not-the-same'
        response = self.client.post('/signup', data=form_data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.query.count(), 0)
        self.assertIn(b'Passwords must match', response.data)

    def test_signup_rejects_lga_from_a_different_state(self):
        another_state = State(state_name='Kano')
        db.session.add(another_state)
        db.session.flush()
        another_lga = Lga(state_id=another_state.state_id, lga_name='Kano Municipal')
        db.session.add(another_lga)
        db.session.commit()

        response = self.client.post('/signup', data={
            'username': 'Test Shopper',
            'email': 'shopper@example.com',
            'gender': 'Female',
            'dob': '2000-01-02',
            'phone': '12345678',
            'state_id': str(self.state.state_id),
            'lga_id': str(another_lga.lga_id),
            'password': 'secure-pass',
            'confirmpassword': 'secure-pass',
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.query.count(), 0)
        self.assertIn(b'Select a valid state and local government area', response.data)

    def test_lga_endpoint_returns_only_lgas_for_selected_state(self):
        response = self.client.get(
            f'/signup/lgas?state_id={self.state.state_id}'
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), [
            {'id': self.lga.lga_id, 'name': 'Ikeja'},
        ])


if __name__ == '__main__':
    unittest.main()

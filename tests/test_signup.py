import os
import unittest

os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['SECRET_KEY'] = 'signup-test-key'

from pkg import app
from pkg.models import User, db
from werkzeug.security import check_password_hash


class UserSignupTestCase(unittest.TestCase):
    def setUp(self):
        app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            SECRET_KEY='signup-test-key',
        )
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

    def test_signup_saves_user_with_parsed_date_and_hashed_password(self):
        response = self.client.post('/signup', data={
            'username': 'Test Shopper',
            'email': ' Shopper@Example.com ',
            'gender': 'Female',
            'dob': '2000-01-02',
            'phone': '12345678',
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
        self.assertTrue(check_password_hash(user.password, 'secure-pass'))

    def test_signup_rejects_duplicate_email(self):
        db.session.add(User(email='shopper@example.com'))
        db.session.commit()

        response = self.client.post('/signup', data={
            'username': 'Test Shopper',
            'email': 'SHOPPER@example.com',
            'gender': 'Female',
            'dob': '2000-01-02',
            'phone': '12345678',
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


if __name__ == '__main__':
    unittest.main()

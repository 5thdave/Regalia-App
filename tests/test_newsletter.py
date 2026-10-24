import os
import unittest

os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['SECRET_KEY'] = 'newsletter-test-key'

from pkg import app
from pkg.models import NewsletterSubscriber, User, db


class NewsletterSubscriptionTestCase(unittest.TestCase):
    def setUp(self):
        app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            SECRET_KEY='newsletter-test-key',
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

    def test_valid_email_is_normalized_and_saved(self):
        response = self.client.post(
            '/newsletter/subscribe',
            data={'email': '  Shopper@Example.com  '},
        )

        self.assertEqual(response.status_code, 302)
        subscriber = NewsletterSubscriber.query.one()
        self.assertEqual(subscriber.email, 'shopper@example.com')
        self.assertIsNotNone(subscriber.subscribed_at)

    def test_invalid_emails_are_rejected_without_saving(self):
        for email in ('', 'not-an-email', 'no-domain@example', 'a b@example.com'):
            with self.subTest(email=email):
                response = self.client.post(
                    '/newsletter/subscribe',
                    data={'email': email},
                )
                self.assertEqual(response.status_code, 302)
                self.assertEqual(NewsletterSubscriber.query.count(), 0)

    def test_duplicate_email_does_not_create_duplicate_subscriber(self):
        self.client.post(
            '/newsletter/subscribe',
            data={'email': 'shopper@example.com'},
        )

        response = self.client.post(
            '/newsletter/subscribe',
            data={'email': 'SHOPPER@example.com'},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(NewsletterSubscriber.query.count(), 1)

    def test_homepage_displays_social_links_and_newsletter_form(self):
        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn('aria-label="Regalia social media"', page)
        self.assertIn('aria-label="Visit Instagram"', page)
        self.assertIn('aria-label="Visit Twitter"', page)
        self.assertIn('action="/newsletter/subscribe"', page)
        self.assertIn('name="email"', page)

    def test_signed_in_homepage_displays_newsletter_and_sticky_social_links(self):
        user = User(
            name='Signed In Shopper',
            email='signed-in@example.com',
            status='Active',
        )
        db.session.add(user)
        db.session.commit()
        with self.client.session_transaction() as session:
            session['useronline'] = user.id

        response = self.client.get('/user/')

        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn('aria-label="Regalia social media"', page)
        self.assertIn('aria-label="Visit Instagram"', page)
        self.assertIn('aria-label="Visit Twitter"', page)
        self.assertIn('class="newsletter-signup"', page)
        self.assertIn('action="/newsletter/subscribe"', page)
        self.assertIn('style.css?v=2', page)


if __name__ == '__main__':
    unittest.main()

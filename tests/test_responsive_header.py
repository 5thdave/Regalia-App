import os
import unittest

os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['SECRET_KEY'] = 'responsive-test-key'

from pkg import app
from pkg.models import db


class ResponsiveHeaderTestCase(unittest.TestCase):
    def setUp(self):
        app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            SECRET_KEY='responsive-test-key',
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

    def test_homepage_contains_nav_toggle_and_main_nav(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        # Nav toggle button exists with accessibility attributes
        self.assertIn('id="nav-toggle"', html)
        self.assertIn('aria-controls="main-nav"', html)
        self.assertIn('icon-hamburger', html)
        self.assertIn('icon-close', html)

        # Navigation container has id="main-nav"
        self.assertIn('id="main-nav"', html)
        self.assertIn('class="nav"', html)

        # Logo link exists
        self.assertIn('class="logo"', html)
        self.assertIn('REGALIA', html)

    def test_css_contains_responsive_rules_for_logo_and_dropdown(self):
        response = self.client.get('/static/css/style.css')
        self.assertEqual(response.status_code, 200)
        css = response.get_data(as_text=True)

        # Non-mobile view sets nav-toggle display: none !important
        self.assertIn('.nav-toggle', css)
        self.assertIn('display: none !important', css)

        # Mobile view breakpoint (max-width: 768px)
        self.assertIn('@media (max-width: 768px)', css)
        self.assertIn('.logo span', css)

        # Nav becomes dropdown menu
        self.assertIn('.nav.is-open', css)

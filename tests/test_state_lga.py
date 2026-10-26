import os
import unittest

os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['SECRET_KEY'] = 'state-lga-test-key'

from pkg import app
from pkg.models import db, State, Lga
from pkg.seed import seed_states_and_lgas


class StateLgaModelTestCase(unittest.TestCase):
    def setUp(self):
        app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            SECRET_KEY='state-lga-test-key',
        )
        self.app_context = app.app_context()
        self.app_context.push()
        db.drop_all()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.app_context.pop()

    def test_state_and_lga_creation_and_relationship(self):
        state = State(state_name='Lagos')
        db.session.add(state)
        db.session.commit()

        lga1 = Lga(state_id=state.state_id, lga_name='Ikeja')
        lga2 = Lga(state_id=state.state_id, lga_name='Surulere')
        db.session.add_all([lga1, lga2])
        db.session.commit()

        queried_state = State.query.filter_by(state_name='Lagos').first()
        self.assertIsNotNone(queried_state)
        self.assertEqual(len(queried_state.lgas), 2)
        lga_names = [l.lga_name for l in queried_state.lgas]
        self.assertIn('Ikeja', lga_names)
        self.assertIn('Surulere', lga_names)
        self.assertEqual(lga1.state.state_name, 'Lagos')

    def test_seed_states_and_lgas_populates_all_records(self):
        self.assertEqual(State.query.count(), 0)
        self.assertEqual(Lga.query.count(), 0)

        seed_states_and_lgas()

        self.assertEqual(State.query.count(), 38)
        self.assertEqual(Lga.query.count(), 788)

        # Verify a specific state and its LGAs
        kano = State.query.filter_by(state_name='Kano').first()
        self.assertIsNotNone(kano)
        self.assertTrue(len(kano.lgas) > 0)

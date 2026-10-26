import os
from pkg.models import db, Color, Size, State, Lga

DEFAULT_COLORS = [
    ("Onyx Black", "#0F0F0F"),
    ("Ivory White", "#F8F6F0"),
    ("Lilac Ash", "#BCABAE"),
    ("Graphite", "#2D2E2E"),
    ("Champagne Gold", "#F7E7CE"),
    ("Emerald Green", "#046307"),
    ("Royal Burgundy", "#800020"),
    ("Midnight Navy", "#1B263B"),
    ("Terracotta", "#E2725B"),
    ("Ochre Gold", "#CC7722"),
    ("Camel", "#C19A6B"),
    ("Cloud Gray", "#D3D3D3"),
]

DEFAULT_SIZES = [
    ("XS", "Extra Small", 1),
    ("S", "Small", 2),
    ("M", "Medium", 3),
    ("L", "Large", 4),
    ("XL", "Extra Large", 5),
    ("XXL", "Double Extra Large", 6),
    ("One Size", "Universal", 7),
]


def seed_states_and_lgas():
    try:
        sql_path = os.path.join(os.path.dirname(__file__), 'nigeria_state_lg.sql')
        if not os.path.exists(sql_path):
            return

        with open(sql_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        if State.query.count() == 0:
            states_data = []
            is_state = False
            for line in lines:
                if 'INSERT INTO `state`' in line:
                    is_state = True
                    continue
                if is_state:
                    clean = line.strip().rstrip(',;')
                    if clean.startswith('(') and clean.endswith(')'):
                        parts = clean[1:-1].split(',', 1)
                        states_data.append(State(state_id=int(parts[0].strip()), state_name=parts[1].strip().strip("'")))
                    if line.strip().endswith(';'):
                        break

            if states_data:
                db.session.add_all(states_data)
                db.session.commit()

        if Lga.query.count() == 0:
            lgas_data = []
            is_lga = False
            for line in lines:
                if 'INSERT INTO `lga`' in line:
                    is_lga = True
                    continue
                if is_lga:
                    clean = line.strip().rstrip(',;')
                    if clean.startswith('(') and clean.endswith(')'):
                        parts = clean[1:-1].split(',', 2)
                        lgas_data.append(Lga(lga_id=int(parts[0].strip()), state_id=int(parts[1].strip()), lga_name=parts[2].strip().strip("'")))
                    if line.strip().endswith(';'):
                        break

            if lgas_data:
                db.session.add_all(lgas_data)
                db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Seed states/lgas note: {e}")


def seed_defaults():
    try:
        # Ensure tables exist
        db.create_all()

        # Seed colors if empty
        if Color.query.count() == 0:
            for name, hex_code in DEFAULT_COLORS:
                db.session.add(Color(color_name=name, hex_code=hex_code))
            db.session.commit()

        # Seed sizes if empty
        if Size.query.count() == 0:
            for code, name, sort_order in DEFAULT_SIZES:
                db.session.add(Size(size_code=code, size_name=name, sort_order=sort_order))
            db.session.commit()

        # Seed states and LGAs if empty
        seed_states_and_lgas()
    except Exception as e:
        db.session.rollback()
        print(f"Seed defaults note: {e}")

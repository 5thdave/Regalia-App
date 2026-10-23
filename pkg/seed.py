from pkg.models import db, Color, Size

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
    except Exception as e:
        db.session.rollback()
        print(f"Seed defaults note: {e}")

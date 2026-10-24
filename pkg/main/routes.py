from flask import  Blueprint, abort, current_app, flash, jsonify, render_template, request, redirect,url_for,  session
from sqlalchemy import and_, func, or_
from sqlalchemy.exc import SQLAlchemyError
from pkg.models import (
    db,
    User,
    Brand,
    BrandLogo,
    Category,
    FavoriteBrand,
    Wishlist,
    Product,
    ProductImage,
    ProductVariant,
    Size,
    Admin,
)

from sqlalchemy.orm import selectinload
from werkzeug.security import check_password_hash, generate_password_hash


main = Blueprint('main', __name__, template_folder='templates', static_folder='static')


@main.errorhandler(SQLAlchemyError)
def handle_database_error(error):
    current_app.logger.exception('Database error in main route: %s', error)
    db.session.rollback()
    message = 'Something went wrong while accessing the database. Please try again.'

    if request.path.startswith('/shopcollection/') and '/filter/' in request.path:
        return jsonify({'error': message}), 503

    flash(message, 'error')
    return render_template('main/error.html'), 503


@main.route('/')
def index():
    featured_brands = (
        db.session.query(Brand, BrandLogo.logo)
        .join(BrandLogo, BrandLogo.brand_id == Brand.brand_id)
        .filter(BrandLogo.logo.isnot(None), BrandLogo.logo != '')
        .all()
    )
    user_id = session.get('useronline')
    favorite_brand_ids = set()
    if user_id:
        favorite_brand_ids = set(
            db.session.query(FavoriteBrand.brand_id)
            .filter_by(user_id=user_id)
            .all()
        )
        favorite_brand_ids = {brand_id for (brand_id,) in favorite_brand_ids}
    return render_template(
        'main/index.html',
        featured_brands=featured_brands,
        favorite_brand_ids=favorite_brand_ids,
    )


@main.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        login_type = request.form.get('login_type')

        if login_type == 'brand':
            brand = Brand.query.filter_by(brand_email=email).first()
            if brand and check_password_hash(brand.password, password):
                session.clear()
                session['brandonline'] = brand.brand_id
                flash('You are now logged in as a brand.', 'success')
                return redirect(url_for('vendor.vendor_dash'))
        else:
            user = User.query.filter_by(email=email).first()
            if user and check_password_hash(user.password, password):
                if user.status != 'Active':
                    flash('This account is not active. Please contact support.', 'error')
                    return render_template('main/login.html')
                session.clear()
                session['useronline'] = user.id
                
                flash('You are now logged in.', 'success')
                return redirect(url_for('user.user_home'))

        flash('Invalid email or password.', 'error')

    return render_template('main/login.html')


@main.route('/signup', methods=['GET', 'POST'])
def user_signup():
    if request.method == 'POST':
        name = request.form.get('username')
        email = request.form.get('email')
        gender = request.form.get('gender')
        dob = request.form.get('dob')
        phone = request.form.get('phone')
        address = request.form.get('address')
        password = request.form.get('password')
        confirmpass = request.form.get('confirmpassword')
        if password and password == confirmpass:
            password_hash = generate_password_hash(password)
            user = User(
                name=name,
                gender=gender,
                email=email,
                dateofbirth=dob,
                phone=phone,
                country="Nigeria",
                address=address,
                password=password_hash
            )
            db.session.add(user)
            db.session.commit()
            flash('Your account has been created. Please log in.', 'success')
            return redirect(url_for('main.login'))
        flash('Passwords must match.', 'error')
        return render_template('main/signup.html')
    return render_template('main/signup.html')


@main.route('/shop')
def shop():
    brands = Brand.query.all()
    logos = BrandLogo.query.all()
    brand_logos = {logo.brand_id: logo.logo for logo in logos}
    user_id = session.get('useronline')
    brand_id = session.get('brandonline')
    user = db.session.get(User, user_id) if user_id else None
    favorite_brand_ids = (
        {
            brand_id
            for (brand_id,) in db.session.query(FavoriteBrand.brand_id)
            .filter_by(user_id=user_id)
            .all()
        }
        if user_id
        else set()
    )
    return render_template(
        'main/shop.html',
        brands=brands,
        brand_logos=brand_logos,
        favorite_brand_ids=favorite_brand_ids,
        user=user,
        useronline=user_id,
        brandonline=brand_id,
    )


@main.route('/shopcollection')
def shopcollection_redirect():
    return redirect(url_for('main.shop'))


@main.route('/shopcollection/<int:brand_id>')
def shopcollection(brand_id):
    brand = Brand.query.filter_by(brand_id=brand_id).first_or_404()
    brand_logo = BrandLogo.query.filter_by(brand_id=brand_id).first()
    brand_logo_url = (
        url_for('static', filename='media/brandlogos/' + brand_logo.logo)
        if brand_logo and brand_logo.logo
        else None
    )
    stmt = (
        db.select(Product)
        .where(Product.brand_id == brand_id)
        .options(
            selectinload(Product.images).selectinload(ProductImage.color),
            selectinload(Product.variants).selectinload(ProductVariant.color),
            selectinload(Product.variants).selectinload(ProductVariant.size),
        )
    )
    products = db.session.scalars(stmt).all()
    user_id = session.get('useronline')
    wishlisted_product_ids = set()
    if user_id:
        wishlisted_product_ids = set(
            db.session.scalars(
                db.select(Wishlist.wishlistproduct_id).where(
                    Wishlist.wishlistuser_id == user_id
                )
            ).all()
        )
    product_details = [
        {
            'id': product.product_id,
            'name': product.product_name or '',
            'brandName': brand.brand_name or '',
            'description': product.description or '',
            'status': product.status or '',
            'price': float(product.price) if product.price is not None else None,
            'images': [
                {
                    'url': url_for('static', filename='media/' + image.image),
                    'color_id': image.color_id,
                    'color_name': image.color.color_name if image.color else None,
                }
                for image in product.images
                if image.image
            ],
            'variants': [
                {
                    'id': variant.variant_id,
                    'color_id': variant.color_id,
                    'color_name': variant.color.color_name if variant.color else 'Default',
                    'color_hex': variant.color.hex_code if variant.color else '#777777',
                    'size_code': variant.size.size_code if variant.size else 'One size',
                    'size_name': variant.size.size_name if variant.size else '',
                    'price': (
                        float(variant.price if variant.price is not None else product.price)
                        if variant.price is not None or product.price is not None
                        else None
                    ),
                    'stock': variant.stock_quantity or 0,
                }
                for variant in product.variants
            ],
        }
        for product in products
    ]
    user = db.session.get(User, user_id) if user_id else None
    return render_template(
        'main/shopcollection.html',
        brand=brand,
        brand_logo_url=brand_logo_url,
        products=products,
        product_details=product_details,
        user=user,
        useronline=user_id,
        wishlisted_product_ids=wishlisted_product_ids,
    )


def _filtered_collection_product_ids(brand_id):
    if db.session.get(Brand, brand_id) is None:
        abort(404)

    statuses = request.args.getlist('availability')
    price_ranges = request.args.getlist('price')
    sizes = [value.lower() for value in request.args.getlist('size')]
    categories = [value.lower() for value in request.args.getlist('category')]

    if any(status not in {'Available', 'Out of Stock'} for status in statuses):
        abort(400, description='Invalid availability filter.')
    if any(value not in {'under-500', '500-1000', 'over-1000'} for value in price_ranges):
        abort(400, description='Invalid price filter.')
    if any(value not in {'s', 'm', 'l', 'xl'} for value in sizes):
        abort(400, description='Invalid size filter.')
    if any(value not in {'apparel', 'outerwear', 'accessories'} for value in categories):
        abort(400, description='Invalid category filter.')

    stmt = db.select(Product.product_id).where(Product.brand_id == brand_id)
    if statuses:
        stmt = stmt.where(Product.status.in_(statuses))
    if price_ranges:
        range_filters = []
        if 'under-500' in price_ranges:
            range_filters.append(and_(Product.price.isnot(None), Product.price < 500))
        if '500-1000' in price_ranges:
            range_filters.append(
                and_(Product.price >= 500, Product.price <= 1000)
            )
        if 'over-1000' in price_ranges:
            range_filters.append(Product.price > 1000)
        stmt = stmt.where(or_(*range_filters))
    if sizes:
        stmt = stmt.where(
            Product.variants.any(
                ProductVariant.size.has(func.lower(Size.size_code).in_(sizes))
            )
        )
    if categories:
        stmt = stmt.where(
            Product.category.has(
                func.lower(Category.category_name).in_(categories)
            )
        )

    return jsonify({'product_ids': db.session.scalars(stmt).all()})


@main.get('/shopcollection/<int:brand_id>/filter/availability')
def filter_collection_availability(brand_id):
    return _filtered_collection_product_ids(brand_id)


@main.get('/shopcollection/<int:brand_id>/filter/price')
def filter_collection_price(brand_id):
    return _filtered_collection_product_ids(brand_id)


@main.get('/shopcollection/<int:brand_id>/filter/size')
def filter_collection_size(brand_id):
    return _filtered_collection_product_ids(brand_id)


@main.get('/shopcollection/<int:brand_id>/filter/category')
def filter_collection_category(brand_id):
    return _filtered_collection_product_ids(brand_id)

@main.route('/adduser')
def addusers():
    password = generate_password_hash('admin12345')
    admin = Admin(name='Mr David',email='admin@gmail.com',password=password)
    db.session.add(admin)
    db.session.commit()
    return 'Admin Added'
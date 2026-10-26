import re
from smtplib import SMTPException
from datetime import date
from flask_mail import Message
from flask import  Blueprint, abort, current_app, flash, jsonify, render_template, request, redirect,url_for,  session
from sqlalchemy import and_, func, or_
from pkg.extensions import mail
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
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
    NewsletterSubscriber,
    Review,
    Order,
    OrderItem,
    Payment,
    State,
    Lga,
)

from sqlalchemy.orm import selectinload
from werkzeug.security import check_password_hash, generate_password_hash


main = Blueprint('main', __name__, template_folder='templates', static_folder='static')


def _product_review_details(product):
    ordered_reviews = sorted(
        product.reviews,
        key=lambda review: (
            review.created_at is not None,
            review.created_at,
            review.review_id,
        ),
        reverse=True,
    )
    rated_reviews = [
        review for review in ordered_reviews
        if review.rating is not None and 1 <= review.rating <= 5
    ]
    return {
        'average_rating': (
            sum(review.rating for review in rated_reviews) / len(rated_reviews)
            if rated_reviews
            else None
        ),
        'review_count': len(rated_reviews),
        'reviews': [
            {
                'rating': (
                    review.rating
                    if review.rating is not None and 1 <= review.rating <= 5
                    else None
                ),
                'comment': review.comment or '',
                'reviewer': (
                    review.user.name
                    if review.user and review.user.name
                    else 'Customer'
                ),
                'verified_purchase': review.order_item_id is not None,
                'created_at': (
                    review.created_at.strftime('%b %d, %Y')
                    if review.created_at
                    else ''
                ),
            }
            for review in ordered_reviews
        ],
    }


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


@main.post('/newsletter/subscribe')
def newsletter_subscribe():
    email = (request.form.get('email') or '').strip().lower()
    if (
        len(email) > 254
        or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email)
    ):
        flash('Enter a valid email address to subscribe.', 'error')
        return redirect(url_for('main.index'))

    subscriber = NewsletterSubscriber(email=email)
    db.session.add(subscriber)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        if NewsletterSubscriber.query.filter_by(email=email).first() is None:
            raise

    flash('Thanks for subscribing to the Regalia newsletter.', 'success')
    return redirect(url_for('main.index'))


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
        name = (request.form.get('username') or '').strip()
        email = (request.form.get('email') or '').strip().lower()
        gender = request.form.get('gender') or None
        dob_value = request.form.get('dob') or ''
        phone = (request.form.get('phone') or '').strip()
        state_value = request.form.get('state_id') or ''
        lga_value = request.form.get('lga_id') or ''
        address = (request.form.get('address') or '').strip()
        password = request.form.get('password') or ''
        confirmpass = request.form.get('confirmpassword') or ''

        if not name or not email or not phone or not dob_value or not password or not state_value or not lga_value:
            flash('Please complete all required fields.', 'error')
        elif gender not in (None, 'Male', 'Female', 'Other'):
            flash('Select a valid gender.', 'error')
        elif len(password) < 8:
            flash('Password must be at least 8 characters long.', 'error')
        elif password != confirmpass:
            flash('Passwords must match.', 'error')
        elif User.query.filter_by(email=email).first():
            flash('An account with that email already exists. Please log in.', 'error')
        else:
            try:
                dob = date.fromisoformat(dob_value)
            except ValueError:
                flash('Enter a valid date of birth.', 'error')
            else:
                try:
                    state_id = int(state_value)
                    lga_id = int(lga_value)
                except ValueError:
                    flash('Select a valid state and local government area.', 'error')
                    state_id = None
                    lga_id = None
                if state_id is not None and lga_id is not None:
                    state = db.session.get(State, state_id)
                    lga = db.session.get(Lga, lga_id)
                    if state is None or lga is None or lga.state_id != state.state_id:
                        flash('Select a valid state and local government area.', 'error')
                    else:
                        user = User(
                            name=name,
                            gender=gender,
                            email=email,
                            dateofbirth=dob,
                            phone=phone,
                            country='Nigeria',
                            state_id=state.state_id,
                            lga_id=lga.lga_id,
                            address=address or None,
                            password=generate_password_hash(password),
                        )
                        db.session.add(user)
                        try:
                            db.session.commit()
                        except IntegrityError:
                            db.session.rollback()
                            user = User.query.filter_by(email=email).first()
                            if user is None:
                                raise
                            flash('An account with that email already exists. Please log in.', 'error')
                        else:
                            sender = current_app.config.get('MAIL_DEFAULT_SENDER')
                            username = current_app.config.get('MAIL_USERNAME')
                            password = current_app.config.get('MAIL_PASSWORD')
                            if sender and username and password:
                                message = Message(
                                    subject='Welcome to Regalia',
                                    sender=sender,
                                    recipients=[user.email],
                                    body=f'Welcome to Regalia, {user.name}. Your account has been created successfully.',
                                )
                                try:
                                    mail.send(message)
                                except (OSError, SMTPException):
                                    current_app.logger.exception(
                                        'Account was created, but its confirmation email could not be sent.'
                                    )
                                    flash(
                                        'Your account was created, but we could not send the confirmation email. Please contact support.',
                                        'error',
                                    )
                                else:
                                    flash('Your account has been created. Please log in.', 'success')
                            else:
                                current_app.logger.error(
                                    'Account confirmation email not sent because mail credentials are not configured.'
                                )
                                flash(
                                    'Your account was created, but email delivery is not configured. Please contact support.',
                                    'error',
                                )
                            return redirect(url_for('main.login'))

    states = State.query.order_by(State.state_name).all()
    return render_template('main/signup.html', states=states)


@main.get('/signup/lgas')
def signup_lgas():
    state_value = request.args.get('state_id', '')
    try:
        state_id = int(state_value)
    except (TypeError, ValueError):
        return jsonify({'error': 'Select a valid state.'}), 400

    if db.session.get(State, state_id) is None:
        return jsonify({'error': 'Select a valid state.'}), 404

    lgas = (
        Lga.query.filter_by(state_id=state_id)
        .order_by(Lga.lga_name)
        .all()
    )
    return jsonify([
        {'id': lga.lga_id, 'name': lga.lga_name}
        for lga in lgas
    ])


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
            selectinload(Product.reviews).joinedload(Review.user),
        )
    )
    products = db.session.scalars(stmt).all()
    product_ids = [product.product_id for product in products]
    user_id = session.get('useronline')
    wishlisted_product_ids = set()
    reviewed_product_ids = set()
    review_order_item_ids = {}
    if user_id:
        wishlisted_product_ids = set(
            db.session.scalars(
                db.select(Wishlist.wishlistproduct_id).where(
                    Wishlist.wishlistuser_id == user_id
                )
            ).all()
        )
        reviewed_product_ids = set(
            db.session.scalars(
                db.select(Review.product_id).where(
                    Review.user_id == user_id,
                    Review.product_id.in_(product_ids),
                )
            ).all()
        )
        if product_ids:
            eligible_order_items = (
                db.session.query(OrderItem.itemproduct_id, OrderItem.orderitem_id)
                .join(Order, Order.order_id == OrderItem.itemorder_id)
                .join(Payment, Payment.paymentorder_id == Order.order_id)
                .filter(
                    Order.orderuser_id == user_id,
                    Order.order_status != 'Cancelled',
                    Payment.status == 'Completed',
                    OrderItem.itemproduct_id.in_(product_ids),
                )
                .order_by(Order.order_date.desc(), OrderItem.orderitem_id.desc())
                .all()
            )
            for product_id, order_item_id in eligible_order_items:
                review_order_item_ids.setdefault(product_id, order_item_id)
    product_review_summaries = {
        product.product_id: _product_review_details(product)
        for product in products
    }
    product_details = [
        {
            'id': product.product_id,
            'name': product.product_name or '',
            'brandName': brand.brand_name or '',
            'description': product.description or '',
            'status': product.status or '',
            'price': float(product.price) if product.price is not None else None,
            **product_review_summaries[product.product_id],
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
        reviewed_product_ids=reviewed_product_ids,
        review_order_item_ids=review_order_item_ids,
        product_review_summaries={
            product_id: {
                'average': summary['average_rating'],
                'count': summary['review_count'],
            }
            for product_id, summary in product_review_summaries.items()
        },
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

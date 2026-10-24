from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

from flask import Blueprint, flash, render_template, request, redirect, url_for, session
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload, selectinload
from pkg.models import (
    db,
    Admin,
    Brand,
    User,
    Category,
    Color,
    Order,
    OrderItem,
    Payment,
    Payout,
    Product,
    Review,
)
from werkzeug.security import check_password_hash


admin = Blueprint('admin', __name__, template_folder='templates', static_folder='static')


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@admin.before_request
def require_admin_session():
    admin_id = session.get('admin_id')
    if request.endpoint != 'admin.login' and (
        session.get('role') != 'admin'
        or not admin_id
        or db.session.get(Admin, admin_id) is None
    ):
        session.pop('admin_id', None)
        session.pop('role', None)
        return redirect(url_for('admin.login'))


@admin.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        admin_user = Admin.query.filter_by(email=email).first()

        if admin_user and check_password_hash(admin_user.password, password):
            session.clear()
            session['admin_id'] = admin_user.id
            session['role'] = 'admin'
            return redirect(url_for('admin.admin_dashboard'))

        flash('Invalid email or password.', 'error')

    return render_template('admin/login.html')


@admin.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for('admin.login'))


@admin.route('/')
def admin_dashboard():
    total_revenue = db.session.query(
        func.coalesce(func.sum(Payment.amount), 0)
    ).filter(Payment.status == 'Completed').scalar()
    total_commission = db.session.query(
        func.coalesce(func.sum(Payout.commission_amount), 0)
    ).scalar()
    pending_payouts = db.session.query(
        func.coalesce(func.sum(Payout.net_amount), 0)
    ).filter(Payout.status == 'Pending').scalar()
    recent_orders = Order.query.options(
        joinedload(Order.user),
    ).order_by(Order.order_date.desc(), Order.order_id.desc()).limit(5).all()

    return render_template(
        'admin/index.html',
        total_revenue=total_revenue,
        total_commission=total_commission,
        brand_count=Brand.query.count(),
        pending_payouts=pending_payouts,
        recent_orders=recent_orders,
    )


@admin.route('/brands')
def brands():
    search = request.args.get('q', '').strip()
    brand_query = Brand.query.order_by(Brand.brand_name)
    if search:
        brand_query = brand_query.filter(or_(
            Brand.brand_name.ilike(f'%{search}%'),
            Brand.brand_email.ilike(f'%{search}%'),
            Brand.brand_phone.ilike(f'%{search}%'),
        ))
    return render_template(
        'admin/brands.html',
        brands=brand_query.all(),
        search=search,
    )

@admin.route('/orders')
def orders():
    search = request.args.get('q', '').strip()
    order_status = request.args.get('order_status', '').strip()
    payment_status = request.args.get('payment_status', '').strip()
    order_statuses = ['Pending', 'Processing', 'Shipped', 'Delivered', 'Cancelled']
    payment_statuses = ['Pending', 'Completed', 'Failed', 'Refunded']

    order_query = Order.query.options(
        joinedload(Order.user),
        selectinload(Order.payments),
    ).order_by(Order.order_date.desc(), Order.order_id.desc())
    if search:
        search_filters = [
            User.name.ilike(f'%{search}%'),
            User.email.ilike(f'%{search}%'),
            Payment.transaction_ref.ilike(f'%{search}%'),
        ]
        if search.isdigit():
            search_filters.append(Order.order_id == int(search))
        order_query = (
            order_query.outerjoin(User, Order.orderuser_id == User.id)
            .outerjoin(Payment, Payment.paymentorder_id == Order.order_id)
            .filter(or_(*search_filters))
            .distinct()
        )
    if order_status in order_statuses:
        order_query = order_query.filter(Order.order_status == order_status)
    orders = order_query.all()

    payment_query = Payment.query.options(
        joinedload(Payment.order),
        joinedload(Payment.user),
    ).order_by(Payment.time_created.desc(), Payment.payment_id.desc())
    if search:
        payment_filters = [
            Payment.transaction_ref.ilike(f'%{search}%'),
            User.name.ilike(f'%{search}%'),
            User.email.ilike(f'%{search}%'),
        ]
        if search.isdigit():
            payment_filters.extend([
                Payment.payment_id == int(search),
                Payment.paymentorder_id == int(search),
            ])
        payment_query = (
            payment_query.join(User, Payment.paymentuser_id == User.id)
            .filter(or_(*payment_filters))
        )
    if payment_status in payment_statuses:
        payment_query = payment_query.filter(Payment.status == payment_status)

    return render_template(
        'admin/orders.html',
        orders=orders,
        payments=payment_query.all(),
        search=search,
        order_status=order_status,
        payment_status=payment_status,
        order_statuses=order_statuses,
        payment_statuses=payment_statuses,
    )


@admin.route('/orders/<int:order_id>')
def order_detail(order_id):
    order = Order.query.options(
        joinedload(Order.user),
        selectinload(Order.items).joinedload(OrderItem.product).joinedload(Product.brand),
        selectinload(Order.items).joinedload(OrderItem.variant),
        selectinload(Order.payments),
    ).filter_by(order_id=order_id).first_or_404()
    return render_template('admin/order_detail.html', order=order)

@admin.route('/categories', methods=['GET', 'POST'])
def categories():
    if request.method == 'POST':
        name = request.form.get('category_name', '').strip()
        description = request.form.get('description', '').strip()
        if not name or len(name) > 100:
            flash('Enter a category name of 1 to 100 characters.', 'error')
            return redirect(url_for('admin.categories'))
        if Category.query.filter(Category.category_name.ilike(name)).first():
            flash('A category with that name already exists.', 'error')
            return redirect(url_for('admin.categories'))

        db.session.add(Category(category_name=name, description=description or None))
        db.session.commit()
        flash('Category added.', 'success')
        return redirect(url_for('admin.categories'))

    categories = Category.query.options(
        selectinload(Category.products)
    ).order_by(Category.category_name).all()
    return render_template('admin/categories.html', category=categories)


@admin.route('/colors', methods=['GET', 'POST'])
def colors():
    if request.method == 'POST':
        name = request.form.get('color_name', '').strip()
        hex_code = request.form.get('hex_code', '').strip()
        if not name or len(name) > 100 or not re.fullmatch(r'#[0-9A-Fa-f]{3}(?:[0-9A-Fa-f]{3})?', hex_code):
            flash('Enter a color name and a valid 3- or 6-digit hex code.', 'error')
            return redirect(url_for('admin.colors'))
        existing = Color.query.filter(Color.color_name.ilike(name)).first()
        if existing:
            flash('A color with that name already exists.', 'error')
            return redirect(url_for('admin.colors'))
        db.session.add(Color(color_name=name, hex_code=hex_code.upper()))
        db.session.commit()
        flash('Color added to the palette.', 'success')
        return redirect(url_for('admin.colors'))

    colors = Color.query.order_by(Color.color_name).all()
    return render_template('admin/colors.html', colors=colors)


@admin.route('/colors/delete/<int:color_id>', methods=['POST'])
def delete_color(color_id):
    color = db.get_or_404(Color, color_id)
    if color.variants or color.images:
        flash('This color is in use and cannot be deleted.', 'error')
        return redirect(url_for('admin.colors'))
    db.session.delete(color)
    db.session.commit()
    flash('Color deleted.', 'success')
    return redirect(url_for('admin.colors'))

@admin.route('/payouts')
def payouts():
    search = request.args.get('q', '').strip()
    status = request.args.get('status', '').strip()
    payout_statuses = ['Pending', 'Processed', 'Failed']
    payout_query = Payout.query.options(
        joinedload(Payout.brand),
        joinedload(Payout.order),
    ).order_by(Payout.time_created.desc(), Payout.payout_id.desc())

    if search:
        search_filters = [
            Brand.brand_name.ilike(f'%{search}%'),
            Payout.payout_reference.ilike(f'%{search}%'),
        ]
        if search.isdigit():
            search_filters.extend([
                Payout.payout_id == int(search),
                Payout.payoutorder_id == int(search),
            ])
        payout_query = (
            payout_query.join(Brand, Payout.payoutbrand_id == Brand.brand_id)
            .filter(or_(*search_filters))
        )
    if status in payout_statuses:
        payout_query = payout_query.filter(Payout.status == status)

    current_month = _utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    pending_total = db.session.query(func.coalesce(func.sum(Payout.net_amount), 0)).filter(
        Payout.status == 'Pending'
    ).scalar()
    processed_this_month = db.session.query(
        func.coalesce(func.sum(Payout.net_amount), 0)
    ).filter(
        Payout.status == 'Processed',
        Payout.paid_at >= current_month,
    ).scalar()
    total_commission = db.session.query(
        func.coalesce(func.sum(Payout.commission_amount), 0)
    ).scalar()

    eligible_payouts = (
        db.session.query(
            Order.order_id,
            Brand.brand_id,
            Brand.brand_name,
        )
        .join(OrderItem, OrderItem.itemorder_id == Order.order_id)
        .join(Product, Product.product_id == OrderItem.itemproduct_id)
        .join(Brand, Brand.brand_id == Product.brand_id)
        .filter(
            Order.order_status == 'Delivered',
            Order.payments.any(Payment.status == 'Completed'),
            OrderItem.unit_price.isnot(None),
            OrderItem.quantity.isnot(None),
        )
        .group_by(Order.order_id, Brand.brand_id, Brand.brand_name)
        .order_by(Order.order_id.desc(), Brand.brand_name)
        .all()
    )
    existing_payouts = {
        (order_id, brand_id)
        for order_id, brand_id in db.session.query(
            Payout.payoutorder_id, Payout.payoutbrand_id
        ).all()
    }
    eligible_payouts = [
        item for item in eligible_payouts
        if (item.order_id, item.brand_id) not in existing_payouts
    ]

    return render_template(
        'admin/payouts.html',
        payouts=payout_query.all(),
        eligible_payouts=eligible_payouts,
        pending_total=pending_total,
        processed_this_month=processed_this_month,
        total_commission=total_commission,
        search=search,
        status=status,
        payout_statuses=payout_statuses,
    )


@admin.route('/payouts/create', methods=['POST'])
def create_payout():
    selected = request.form.get('order_brand', '')
    commission_value = request.form.get('commission_rate', '').strip()
    try:
        order_id_text, brand_id_text = selected.split(':', maxsplit=1)
        order_id = int(order_id_text)
        brand_id = int(brand_id_text)
        commission_rate = Decimal(commission_value)
        if not commission_rate.is_finite() or not Decimal('0') <= commission_rate <= Decimal('100'):
            raise ValueError
    except (ValueError, InvalidOperation):
        flash('Choose an eligible order and enter a commission rate from 0 to 100.', 'error')
        return redirect(url_for('admin.payouts'))

    payout_lines = (
        db.session.query(OrderItem.quantity, OrderItem.unit_price)
        .join(Product, Product.product_id == OrderItem.itemproduct_id)
        .join(Order, Order.order_id == OrderItem.itemorder_id)
        .filter(
            Order.order_id == order_id,
            Product.brand_id == brand_id,
            Order.order_status == 'Delivered',
            Order.payments.any(Payment.status == 'Completed'),
            OrderItem.quantity.isnot(None),
            OrderItem.unit_price.isnot(None),
        )
        .all()
    )
    if not payout_lines:
        flash('That order is no longer eligible for a payout.', 'error')
        return redirect(url_for('admin.payouts'))
    if Payout.query.filter_by(
        payoutorder_id=order_id,
        payoutbrand_id=brand_id,
    ).first():
        flash('A payout already exists for that brand and order.', 'error')
        return redirect(url_for('admin.payouts'))

    gross_amount = sum(
        (Decimal(unit_price) * quantity for quantity, unit_price in payout_lines),
        start=Decimal('0'),
    ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    commission_amount = (gross_amount * commission_rate / Decimal('100')).quantize(
        Decimal('0.01'),
        rounding=ROUND_HALF_UP,
    )
    payout = Payout(
        payoutbrand_id=brand_id,
        payoutorder_id=order_id,
        gross_amount=gross_amount,
        commission_rate=commission_rate,
        commission_amount=commission_amount,
        net_amount=gross_amount - commission_amount,
        status='Pending',
    )
    db.session.add(payout)
    db.session.commit()
    flash('Pending payout created. Complete the transfer outside the app before recording it as processed.', 'success')
    return redirect(url_for('admin.payouts'))


@admin.route('/payouts/<int:payout_id>/process', methods=['POST'])
def process_payout(payout_id):
    payout = db.get_or_404(Payout, payout_id)
    if payout.status != 'Pending':
        flash('Only pending payouts can be recorded as processed.', 'error')
        return redirect(url_for('admin.payouts'))
    if (
        payout.order is None
        or payout.order.order_status != 'Delivered'
        or not any(payment.status == 'Completed' for payment in payout.order.payments)
    ):
        flash('The order is no longer eligible for payout.', 'error')
        return redirect(url_for('admin.payouts'))

    reference = request.form.get('payout_reference', '').strip()
    if not reference or len(reference) > 100:
        flash('Enter the external transfer reference (up to 100 characters).', 'error')
        return redirect(url_for('admin.payouts'))

    payout.status = 'Processed'
    payout.payout_reference = reference
    payout.paid_at = _utcnow()
    db.session.commit()
    flash('Payout recorded as processed.', 'success')
    return redirect(url_for('admin.payouts'))

@admin.route('/reviews')
def reviews():
    search = request.args.get('q', '').strip()
    rating = request.args.get('rating', '').strip()
    review_query = Review.query.options(
        joinedload(Review.user),
        joinedload(Review.product),
    ).order_by(Review.created_at.desc(), Review.review_id.desc())
    if search:
        review_query = (
            review_query.outerjoin(User, Review.user_id == User.id)
            .outerjoin(Product, Review.product_id == Product.product_id)
            .filter(or_(
                User.name.ilike(f'%{search}%'),
                User.email.ilike(f'%{search}%'),
                Product.product_name.ilike(f'%{search}%'),
            ))
        )
    if rating:
        try:
            parsed_rating = int(rating)
        except ValueError:
            parsed_rating = 0
        if parsed_rating in range(1, 6):
            review_query = review_query.filter(Review.rating == parsed_rating)
        else:
            rating = ''
    return render_template(
        'admin/reviews.html',
        reviews=review_query.all(),
        search=search,
        rating=rating,
    )


@admin.route('/reviews/<int:review_id>/delete', methods=['POST'])
def delete_review(review_id):
    review = db.get_or_404(Review, review_id)
    db.session.delete(review)
    db.session.commit()
    flash('Review removed.', 'success')
    return redirect(url_for('admin.reviews'))

@admin.route('/users')
def users():
    search = request.args.get('q', '').strip()
    status = request.args.get('status', '').strip()
    country = request.args.get('country', '').strip()
    user_query = User.query.order_by(User.time_created.desc(), User.id.desc())
    if search:
        user_query = user_query.filter(or_(
            User.name.ilike(f'%{search}%'),
            User.email.ilike(f'%{search}%'),
        ))
    if status in {'Active', 'Inactive', 'Suspended'}:
        user_query = user_query.filter(User.status == status)
    if country:
        user_query = user_query.filter(User.country == country)

    countries = [
        value for (value,) in db.session.query(User.country)
        .filter(User.country.isnot(None), User.country != '')
        .distinct()
        .order_by(User.country)
        .all()
    ]
    return render_template(
        'admin/users.html',
        users=user_query.all(),
        search=search,
        status=status,
        country=country,
        countries=countries,
    )


@admin.route('/users/<int:user_id>/status', methods=['POST'])
def update_user_status(user_id):
    new_status = request.form.get('status', '')
    if new_status not in {'Active', 'Inactive', 'Suspended'}:
        flash('Choose a valid user status.', 'error')
        return redirect(url_for('admin.users'))

    user = db.get_or_404(User, user_id)
    user.status = new_status
    db.session.commit()
    flash('User status updated.', 'success')
    return redirect(url_for('admin.users'))

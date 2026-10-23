import os
import secrets
from decimal import Decimal, ROUND_HALF_UP
import requests
from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    render_template,
    redirect,
    session,
    url_for,
    request,
)
from pkg.models import db, Brand, Product, ProductImage, ProductVariant, BrandLogo, FavoriteBrand, User, Order,OrderItem, Payment
from sqlalchemy.exc import SQLAlchemyError

from dotenv import load_dotenv

load_dotenv()
user = Blueprint('user', __name__, template_folder='templates', static_folder='static')


@user.errorhandler(SQLAlchemyError)
def handle_database_error(error):
    current_app.logger.exception("Database error in user route: %s", error)
    db.session.rollback()
    message = "Something went wrong while accessing the database. Please try again."
    if request.is_json:
        return jsonify({"error": message}), 503

    flash(message, "error")
    return render_template("user/error.html"), 503


@user.route('/')
def user_home():
    featured_brands = (
        db.session.query(Brand, BrandLogo.logo)
        .join(BrandLogo, BrandLogo.brand_id == Brand.brand_id)
        .filter(BrandLogo.logo.isnot(None), BrandLogo.logo != '')
        .all()
    )
    user_id = session.get('useronline')
    favorite_brand_ids = set()
    if user_id:
        favorite_brand_ids = {
            brand_id
            for (brand_id,) in db.session.query(FavoriteBrand.brand_id)
            .filter_by(user_id=user_id)
            .all()
        }
    return render_template(
        'user/index.html',
        featured_brands=featured_brands,
        favorite_brand_ids=favorite_brand_ids,
    )


@user.route('/profile')
def user_profile():
    user_id = session.get('useronline')
    if user_id is None:
        flash("Please log in to view your profile.", "error")
        return redirect(url_for('main.login'))

    current_user = db.session.get(User, user_id)
    if current_user is None:
        session.pop('useronline', None)
        flash("Please log in again to view your profile.", "error")
        return redirect(url_for('main.login'))

    logo_query = (
        db.select(BrandLogo.logo)
        .where(BrandLogo.brand_id == Brand.brand_id)
        .order_by(BrandLogo.logo_id)
        .limit(1)
        .scalar_subquery()
    )
    favorite_brands = (
        db.session.query(Brand, logo_query)
        .join(FavoriteBrand, FavoriteBrand.brand_id == Brand.brand_id)
        .filter(FavoriteBrand.user_id == current_user.id)
        .order_by(Brand.brand_name)
        .all()
    )
    user_initials = ''.join(
        part[0] for part in (current_user.name or '').split()[:2]
    ).upper() or '?'
    return render_template(
        'user/profile.html',
        profile_user=current_user,
        user_initials=user_initials,
        favorite_brands=favorite_brands,
    )


@user.route('/favorites/<int:brand_id>', methods=['POST'])
def toggle_favorite(brand_id):
    user_id = session.get('useronline')
    if user_id is None:
        flash("Please log in to manage your favorite brands.", "error")
        return redirect(url_for('main.login'))

    current_user = db.session.get(User, user_id)
    if current_user is None:
        session.pop('useronline', None)
        flash("Please log in again to manage your favorite brands.", "error")
        return redirect(url_for('main.login'))

    brand = db.get_or_404(Brand, brand_id)
    favorite = FavoriteBrand.query.filter_by(
        user_id=current_user.id, brand_id=brand.brand_id
    ).first()
    if favorite:
        db.session.delete(favorite)
    else:
        db.session.add(FavoriteBrand(user_id=current_user.id, brand_id=brand.brand_id))
    db.session.commit()
    flash(
        "Brand removed from your favorites." if favorite else "Brand added to your favorites.",
        "success",
    )

    destinations = {
        'main.index': 'main.index',
        'main.shop': 'main.shop',
        'user.user_home': 'user.user_home',
        'user.user_profile': 'user.user_profile',
    }
    destination = destinations.get(request.form.get('return_to'), 'user.user_profile')
    return redirect(url_for(destination))


@user.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for('main.login'))


@user.route('/shop')
def shop():
    return redirect(url_for('main.shop'))


@user.route('/shopcollection/<int:brand_id>')
def shopcollection(brand_id):
    return redirect(url_for('main.shopcollection', brand_id=brand_id))


@user.route("/pay_initialize", methods=["POST"])
@user.route("/pay_initialize/<int:item_id>", methods=["GET", "POST"])
def pay_initialize(item_id=None):
    user_id = session.get("useronline")
    if user_id is None:
        flash("Please log in before starting checkout.", "error")
        return redirect(url_for("main.login"))

    customer = db.session.get(User, user_id)
    if customer is None:
        session.pop("useronline", None)
        flash("Please log in again before starting checkout.", "error")
        return redirect(url_for("main.login"))
    if not customer.email:
        abort(400, description="Your account needs an email address before checkout.")

    variant_ids = request.form.getlist("variant_id")
    quantities = request.form.getlist("quantity")
    if not variant_ids and item_id is not None:
        variant_ids = [str(item_id)]
        quantities = [request.values.get("quantity", "1")]
    if not variant_ids or len(variant_ids) != len(quantities):
        abort(400, description="Select at least one cart item to purchase.")

    requested_quantities = {}
    try:
        for variant_id, quantity_value in zip(variant_ids, quantities):
            parsed_variant_id = int(variant_id)
            parsed_quantity = int(quantity_value)
            if parsed_variant_id < 1 or parsed_quantity < 1:
                raise ValueError
            requested_quantities[parsed_variant_id] = (
                requested_quantities.get(parsed_variant_id, 0) + parsed_quantity
            )
    except (TypeError, ValueError):
        abort(400, description="Cart items must have valid variant IDs and quantities.")

    order_lines = []
    amount = Decimal("0")
    for variant_id, quantity in requested_quantities.items():
        variant = db.session.get(ProductVariant, variant_id)
        if variant is None:
            abort(404, description="A selected product variant no longer exists.")
        product = variant.product
        if product is None or product.status != "Available":
            abort(400, description="A selected product is not available for purchase.")
        if quantity > (variant.stock_quantity or 0):
            abort(400, description="A selected variant does not have enough stock.")

        unit_price = variant.price if variant.price is not None else product.price
        if unit_price is None or unit_price <= 0:
            abort(400, description="A selected product does not have a valid price.")

        unit_price = Decimal(unit_price)
        amount += unit_price * quantity
        order_lines.append((variant, product, quantity, unit_price))

    amount_in_minor_units = int(
        (amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )
    secret_key = current_app.config.get("PAYSTACK_API_SECRET_KEY") or os.getenv(
        "PAYSTACK_API_SECRET_KEY"
    )
    if not secret_key:
        abort(503, description="Payment processing is not configured.")

    reference = f"ORDER-{secrets.token_hex(12)}"
    headers = {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "email": customer.email,
        "amount": amount_in_minor_units,
        "currency": "NGN",
        "reference": reference,
        "callback_url": url_for("user.pay_confirm", _external=True),
    }

    try:
        response = requests.post(
            "https://api.paystack.co/transaction/initialize",
            json=payload,
            headers=headers,
            timeout=15,
        )
        response.raise_for_status()
        result = response.json()
    except requests.RequestException:
        current_app.logger.exception("Paystack transaction initialization failed")
        abort(502, description="Could not connect to the payment provider.")

    data = result.get("data") if isinstance(result, dict) else None
    if (
        not isinstance(result, dict)
        or not result.get("status")
        or not isinstance(data, dict)
        or not data.get("authorization_url")
    ):
        current_app.logger.error("Paystack did not return a valid checkout URL.")
        abort(502, description="The payment provider could not initialize checkout.")

    order = Order(
        orderuser_id=customer.id,
        order_amt=amount,
        order_status="Pending",
    )
    db.session.add(order)
    db.session.flush()

    order_items = [
        OrderItem(
            itemorder_id=order.order_id,
            itemproduct_id=product.product_id,
            itemvariant_id=variant.variant_id,
            quantity=quantity,
            unit_price=unit_price,
        )
        for variant, product, quantity, unit_price in order_lines
    ]
    payment = Payment(
        paymentorder_id=order.order_id,
        paymentuser_id=customer.id,
        transaction_ref=reference,
        amount=amount,
        currency="NGN",
        status="Pending",
        payment_method="Paystack",
        payment_gateway="Paystack",
    )
    db.session.add_all([*order_items, payment])
    db.session.commit()

    return redirect(data["authorization_url"])


@user.route("/pay/confirm/")
def pay_confirm():
    reference = request.args.get("reference") or request.args.get("trxref")
    if not reference:
        abort(400, description="Missing payment reference.")

    payment = Payment.query.filter_by(transaction_ref=reference).first_or_404()
    secret_key = current_app.config.get("PAYSTACK_API_SECRET_KEY") or os.getenv(
        "PAYSTACK_API_SECRET_KEY"
    )
    if not secret_key:
        abort(503, description="Payment processing is not configured.")

    try:
        response = requests.get(
            f"https://api.paystack.co/transaction/verify/{reference}",
            headers={"Authorization": f"Bearer {secret_key}"},
            timeout=15,
        )
        response.raise_for_status()
        result = response.json()
    except requests.RequestException:
        current_app.logger.exception("Paystack transaction verification failed")
        abort(502, description="Could not verify the payment with the provider.")

    data = result.get("data") if isinstance(result, dict) else None
    if not isinstance(result, dict) or not result.get("status") or not isinstance(data, dict):
        current_app.logger.error("Paystack returned an invalid verification response.")
        abort(502, description="The payment provider returned an invalid response.")

    expected_amount = int(
        (Decimal(payment.amount) * 100).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    if (
        data.get("reference") != payment.transaction_ref
        or data.get("amount") != expected_amount
        or data.get("currency") != payment.currency
    ):
        abort(400, description="The verified payment details do not match the order.")

    order = payment.order
    if order is None:
        current_app.logger.error(
            "Payment %s has no associated order.", payment.payment_id
        )
        abort(500, description="The payment is not linked to an order.")

    if payment.status == "Pending":
        if data.get("status") == "success":
            payment.status = "Completed"
            order.order_status = "Processing"
        else:
            payment.status = "Failed"
            order.order_status = "Cancelled"
        db.session.commit()
        flash(
            "Payment completed successfully."
            if payment.status == "Completed"
            else "Payment was not completed.",
            "success" if payment.status == "Completed" else "error",
        )

    order_item = order.items[0] if order.items else None
    if order_item and order_item.product:
        checkout_succeeded = payment.status == "Completed"
        return redirect(
            url_for(
                "main.shopcollection",
                brand_id=order_item.product.brand_id,
                checkout="success" if checkout_succeeded else None,
            )
        )
    return redirect(url_for("main.shop"))

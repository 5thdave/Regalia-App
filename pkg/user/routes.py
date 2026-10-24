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
from sqlalchemy import update
from pkg.models import (
    db,
    Brand,
    Product,
    ProductImage,
    ProductVariant,
    BrandLogo,
    FavoriteBrand,
    Wishlist,
    Review,
    User,
    Order,
    OrderItem,
    Payment,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload, selectinload

from dotenv import load_dotenv

load_dotenv()
user = Blueprint('user', __name__, template_folder='templates', static_folder='static')


class _InsufficientInventory(Exception):
    pass


def _decrement_order_inventory(order):
    requested_quantities = {}
    for item in order.items:
        if item.itemvariant_id is None or item.quantity is None or item.quantity < 1:
            raise _InsufficientInventory
        requested_quantities[item.itemvariant_id] = (
            requested_quantities.get(item.itemvariant_id, 0) + item.quantity
        )

    if not requested_quantities:
        raise _InsufficientInventory

    for variant_id, quantity in requested_quantities.items():
        result = db.session.execute(
            update(ProductVariant)
            .where(
                ProductVariant.variant_id == variant_id,
                ProductVariant.stock_quantity >= quantity,
            )
            .values(stock_quantity=ProductVariant.stock_quantity - quantity)
        )
        if result.rowcount != 1:
            raise _InsufficientInventory


@user.before_request
def require_active_user():
    user_id = session.get('useronline')
    if user_id is None or request.endpoint == 'user.logout':
        return None

    current_user = db.session.get(User, user_id)
    if current_user is None or current_user.status != 'Active':
        session.pop('useronline', None)
        flash('Your account is not active. Please contact support.', 'error')
        return redirect(url_for('main.login'))

    return None


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
    wishlist_items = (
        Wishlist.query
        .filter_by(wishlistuser_id=current_user.id)
        .options(
            joinedload(Wishlist.product).joinedload(Product.brand),
            joinedload(Wishlist.product).selectinload(Product.images),
        )
        .order_by(Wishlist.time_added.desc(), Wishlist.wishlist_id.desc())
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
        wishlist_items=wishlist_items,
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


@user.route('/wishlist/<int:product_id>', methods=['POST'])
def toggle_wishlist(product_id):
    user_id = session.get('useronline')
    if user_id is None:
        flash('Please log in to add products to your wishlist.', 'error')
        return redirect(url_for('main.login'))

    product = db.get_or_404(Product, product_id)
    wishlist_item = Wishlist.query.filter_by(
        wishlistuser_id=user_id,
        wishlistproduct_id=product.product_id,
    ).first()

    if wishlist_item:
        db.session.delete(wishlist_item)
        message = f'{product.product_name or "Product"} removed from your wishlist.'
    else:
        db.session.add(Wishlist(
            wishlistuser_id=user_id,
            wishlistproduct_id=product.product_id,
        ))
        message = f'{product.product_name or "Product"} added to your wishlist.'

    db.session.commit()
    flash(message, 'success')
    if product.brand_id is None:
        return redirect(url_for('main.shop'))
    return redirect(url_for('main.shopcollection', brand_id=product.brand_id))


@user.route('/reviews/<int:product_id>', methods=['POST'])
def add_review(product_id):
    user_id = session.get('useronline')
    if user_id is None:
        flash('Please log in to review products.', 'error')
        return redirect(url_for('main.login'))

    product = db.get_or_404(Product, product_id)
    rating_value = request.form.get('rating', '')
    comment = request.form.get('comment', '').strip()

    try:
        rating = int(rating_value)
    except (TypeError, ValueError):
        rating = 0

    if rating not in range(1, 6):
        flash('Choose a rating from 1 to 5 stars.', 'error')
        if product.brand_id is None:
            return redirect(url_for('main.shop'))
        return redirect(url_for('main.shopcollection', brand_id=product.brand_id))
    if len(comment) > 2000:
        flash('Reviews must be 2,000 characters or fewer.', 'error')
        if product.brand_id is None:
            return redirect(url_for('main.shop'))
        return redirect(url_for('main.shopcollection', brand_id=product.brand_id))

    db.session.add(Review(
        user_id=user_id,
        product_id=product.product_id,
        rating=rating,
        comment=comment or None,
    ))
    db.session.commit()
    flash('Thank you. Your review has been added.', 'success')
    if product.brand_id is None:
        return redirect(url_for('main.shop'))
    return redirect(url_for('main.shopcollection', brand_id=product.brand_id))


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
        "currency": current_app.config["CURRENCY"],
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
        currency=current_app.config["CURRENCY"],
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

    if payment.status == "Pending" and data.get("status") == "success":
        claim = db.session.execute(
            update(Payment)
            .where(
                Payment.payment_id == payment.payment_id,
                Payment.status == "Pending",
            )
            .values(status="Completed")
        )
        if claim.rowcount == 1:
            try:
                _decrement_order_inventory(order)
            except _InsufficientInventory:
                db.session.rollback()
                claim = db.session.execute(
                    update(Payment)
                    .where(
                        Payment.payment_id == payment.payment_id,
                        Payment.status == "Pending",
                    )
                    .values(status="Completed")
                )
                if claim.rowcount == 1:
                    db.session.execute(
                        update(Order)
                        .where(Order.order_id == order.order_id)
                        .values(order_status="Cancelled")
                    )
                    db.session.commit()
                    current_app.logger.error(
                        "Payment %s succeeded, but inventory was unavailable for order %s.",
                        payment.payment_id,
                        order.order_id,
                    )
                    flash(
                        "Your payment succeeded, but the items could not be reserved. "
                        "Please contact support about a refund.",
                        "error",
                    )
                else:
                    db.session.rollback()
                    db.session.refresh(payment)
                    flash(
                        "Payment completed successfully."
                        if payment.status == "Completed"
                        else "Payment was not completed.",
                        "success" if payment.status == "Completed" else "error",
                    )
            else:
                order.order_status = "Processing"
                db.session.commit()
                flash("Payment completed successfully.", "success")
        else:
            db.session.rollback()
            db.session.refresh(payment)
            flash(
                "Payment completed successfully."
                if payment.status == "Completed"
                else "Payment was not completed.",
                "success" if payment.status == "Completed" else "error",
            )
    elif payment.status == "Pending":
        claim = db.session.execute(
            update(Payment)
            .where(
                Payment.payment_id == payment.payment_id,
                Payment.status == "Pending",
            )
            .values(status="Failed")
        )
        if claim.rowcount == 1:
            db.session.execute(
                update(Order)
                .where(Order.order_id == order.order_id)
                .values(order_status="Cancelled")
            )
            db.session.commit()
            flash("Payment was not completed.", "error")
        else:
            db.session.rollback()
            db.session.refresh(payment)
            flash(
                "Payment completed successfully."
                if payment.status == "Completed"
                else "Payment was not completed.",
                "success" if payment.status == "Completed" else "error",
            )

    order_item = order.items[0] if order.items else None
    if order_item and order_item.product:
        checkout_succeeded = (
            payment.status == "Completed" and order.order_status != "Cancelled"
        )
        return redirect(
            url_for(
                "main.shopcollection",
                brand_id=order_item.product.brand_id,
                checkout=(
                    "success"
                    if checkout_succeeded
                    else "inventory_issue"
                    if payment.status == "Completed"
                    else None
                ),
            )
        )
    return redirect(url_for("main.shop"))

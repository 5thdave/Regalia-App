import os
import secrets
from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from pkg.models import db, Brand, Category, Color, Size, Product, ProductVariant, ProductImage, BrandLogo, Order, OrderItem, User
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload


vendor = Blueprint('vendor', __name__, template_folder='templates', static_folder='static')


@vendor.errorhandler(SQLAlchemyError)
def handle_database_error(error):
    current_app.logger.exception("Database error in vendor route: %s", error)
    db.session.rollback()
    flash("Something went wrong while accessing the database. Please try again.", "error")
    return render_template("vendor/error.html"), 503


@vendor.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        password = request.form.get('password')
        confirmpassword = request.form.get('confirmpassword')
        desc = request.form.get('description')
        uploaded_file = request.files.get('brand_logo')
        upload_folder = os.path.join(current_app.root_path, 'static', 'media', 'brandlogos')
        os.makedirs(upload_folder, exist_ok=True)

        if password and password == confirmpassword and uploaded_file and uploaded_file.filename != '':
            password_hash = generate_password_hash(password)
            brand = Brand(
                brand_name=name,
                brand_email=email,
                brand_phone=phone,
                brand_desc=desc,
                password=password_hash,
            )
            db.session.add(brand)
            db.session.flush()

            filename = secure_filename(uploaded_file.filename)
            unique_filename = f"{secrets.token_hex(8)}_{filename}"
            uploaded_file.save(os.path.join(upload_folder, unique_filename))

            logo = BrandLogo(brand_id=brand.brand_id, logo=unique_filename)
            db.session.add(logo)
            db.session.commit()
            flash("Your brand has been registered. Please log in.", "success")
        elif password != confirmpassword:
            flash("The passwords do not match.", "error")
        elif not uploaded_file or not uploaded_file.filename:
            flash("Please upload a logo for your brand.", "error")
        else:
            flash("Please enter a password.", "error")

        return redirect(url_for('main.login'))

    return render_template('vendor/register.html')


@vendor.route('/upload', methods=['GET', 'POST'])
def upload():
    brand_id = session.get('brandonline')
    if not brand_id:
        flash("Please log in as a brand to upload products.", "error")
        return redirect(url_for('main.login'))

    if request.method == 'POST':
        product_name = request.form.get('product_name')
        category_id = request.form.get('category')
        base_price = request.form.get('base_price')
        description = request.form.get('description')
        status = request.form.get('status', 'Available')

        product = Product(
            product_name=product_name,
            brand_id=brand_id,
            category_id=category_id,
            price=base_price,
            description=description,
            status=status
        )
        db.session.add(product)
        db.session.flush()

        # Handle uploaded photos
        uploaded_files = request.files.getlist('product_images')
        image_color_ids = request.form.getlist('product_image_colors[]')
        upload_folder = os.path.join(current_app.root_path, 'static', 'media')
        os.makedirs(upload_folder, exist_ok=True)

        for index, file in enumerate(uploaded_files):
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                unique_filename = f"{secrets.token_hex(8)}_{filename}"
                file.save(os.path.join(upload_folder, unique_filename))
                color_value = image_color_ids[index] if index < len(image_color_ids) else ''
                color_id = int(color_value) if color_value.isdigit() else None
                if color_id is not None and db.session.get(Color, color_id) is None:
                    abort(400, description='Selected image color does not exist.')
                img = ProductImage(
                    product_id=product.product_id,
                    image=unique_filename,
                    color_id=color_id,
                )
                db.session.add(img)

        # Handle variants (color, size, price override, stock)
        variant_color_ids = request.form.getlist('variant_color[]')
        variant_size_ids = request.form.getlist('variant_size[]')
        variant_prices = request.form.getlist('variant_price[]')
        variant_stocks = request.form.getlist('variant_stock[]')

        for i in range(len(variant_color_ids)):
            c_val = variant_color_ids[i] if i < len(variant_color_ids) else None
            s_val = variant_size_ids[i] if i < len(variant_size_ids) else None
            p_val = variant_prices[i] if i < len(variant_prices) else None
            q_val = variant_stocks[i] if i < len(variant_stocks) else 0

            color_id = int(c_val) if c_val and str(c_val).isdigit() else None
            size_id = int(s_val) if s_val and str(s_val).isdigit() else None
            price = float(p_val) if p_val and str(p_val).strip() else base_price
            stock = int(q_val) if q_val and str(q_val).isdigit() else 0

            if color_id or size_id:
                variant = ProductVariant(
                    productvariant_id=product.product_id,
                    color_id=color_id,
                    size_id=size_id,
                    price=price,
                    stock_quantity=stock
                )
                db.session.add(variant)

        db.session.commit()
        flash("Product uploaded successfully.", "success")
        return redirect(url_for('vendor.vendor_dash'))

    categories = Category.query.all()
    colors = Color.query.order_by(Color.color_name).all()
    sizes = Size.query.order_by(Size.sort_order).all()
    return render_template('vendor/upload.html', category=categories, colors=colors, sizes=sizes)


@vendor.route('/dashboard', methods=['GET', 'POST'])
def vendor_dash():
    brand_id = session.get('brandonline')
    if not brand_id:
        flash("Please log in as a brand to access the dashboard.", "error")
        return redirect(url_for('main.login'))

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'update_order_status':
            order_id = request.form.get('order_id')
            new_status = request.form.get('order_status')
            if not order_id or new_status not in ['Pending', 'Processing', 'Shipped', 'Delivered', 'Cancelled']:
                flash("Select a valid order and status.", "error")
                return redirect(url_for('vendor.vendor_dash'))

            try:
                parsed_order_id = int(order_id)
            except ValueError:
                flash("The selected order is invalid.", "error")
                return redirect(url_for('vendor.vendor_dash'))

            order = db.session.get(Order, parsed_order_id)
            item_belongs = (
                db.session.query(OrderItem)
                .join(Product, OrderItem.itemproduct_id == Product.product_id)
                .filter(OrderItem.itemorder_id == parsed_order_id, Product.brand_id == brand_id)
                .first()
            )
            if order and item_belongs:
                order.order_status = new_status
                db.session.commit()
                flash("Order status updated.", "success")
            else:
                flash("The selected order could not be found.", "error")
            return redirect(url_for('vendor.vendor_dash'))

        if action == 'update_stock':
            variant_id = request.form.get('variant_id')
            stock_quantity = request.form.get('stock_quantity')
            try:
                parsed_variant_id = int(variant_id)
                stock_qty = int(stock_quantity)
                if parsed_variant_id < 1 or stock_qty < 0:
                    raise ValueError
            except (TypeError, ValueError):
                flash("Enter a valid variant and non-negative stock quantity.", "error")
                return redirect(url_for('vendor.vendor_dash'))

            variant = db.session.get(ProductVariant, parsed_variant_id)
            if variant and variant.product and variant.product.brand_id == brand_id:
                variant.stock_quantity = stock_qty
                db.session.commit()
                flash("Product stock updated.", "success")
            else:
                flash("The selected product variant could not be found.", "error")
            return redirect(url_for('vendor.vendor_dash'))

        if action == 'delete':
            product_id = request.form.get('product_id')
            try:
                parsed_product_id = int(product_id)
            except (TypeError, ValueError):
                flash("The selected product is invalid.", "error")
                return redirect(url_for('vendor.vendor_dash'))

            product = db.session.get(Product, parsed_product_id)
            if product and product.brand_id == brand_id:
                db.session.delete(product)
                db.session.commit()
                flash("Product deleted.", "success")
            else:
                flash("The selected product could not be found.", "error")
            return redirect(url_for('vendor.vendor_dash'))

    stmt = (
        db.select(Product)
        .where(Product.brand_id == brand_id)
        .options(
            selectinload(Product.images).selectinload(ProductImage.color),
            selectinload(Product.variants).selectinload(ProductVariant.color),
            selectinload(Product.variants).selectinload(ProductVariant.size),
            selectinload(Product.category),
        )
    )
    products = db.session.scalars(stmt).all()
    product_variants = [
        variant
        for product in products
        for variant in product.variants
    ]
    orders = db.session.execute(
        db.select(
            Order.order_id,
            Product.product_name,
            Color.color_name,
            Size.size_code,
            OrderItem.quantity,
            OrderItem.unit_price,
            Order.order_status,
            Order.order_date,
            User.name.label('customer_name'),
            OrderItem.orderitem_id,
        )
        .select_from(OrderItem)
        .join(Order, OrderItem.itemorder_id == Order.order_id)
        .join(Product, OrderItem.itemproduct_id == Product.product_id)
        .outerjoin(User, Order.orderuser_id == User.id)
        .outerjoin(ProductVariant, OrderItem.itemvariant_id == ProductVariant.variant_id)
        .outerjoin(Color, ProductVariant.color_id == Color.color_id)
        .outerjoin(Size, ProductVariant.size_id == Size.size_id)
        .where(Product.brand_id == brand_id)
        .order_by(Order.order_date.desc(), Order.order_id.desc())
    ).all()

    active_orders = [
        o for o in orders
        if (o.order_status or 'Pending') in {'Pending', 'Processing', 'Shipped'}
    ]
    active_orders_count = len({o.order_id for o in active_orders})
    total_revenue = sum((o.quantity or 0) * float(o.unit_price or 0) for o in orders if o.order_status != 'Cancelled')
    units_sold = sum((o.quantity or 0) for o in orders if o.order_status != 'Cancelled')
    low_stock_count = sum(1 for v in product_variants if v.stock_quantity < 5)

    brand = Brand.query.filter_by(brand_id=brand_id).first()
    return render_template(
        'vendor/dashboard.html',
        brand=brand,
        products=products,
        product_count=len(products),
        product_variants=product_variants,
        orders=orders,
        active_orders=active_orders,
        active_orders_count=active_orders_count,
        total_revenue=total_revenue,
        units_sold=units_sold,
        low_stock_count=low_stock_count,
    )


@vendor.route('/profile')
def profile():
    if session.get('brandonline') is not None:
        return render_template('vendor/profile.html')
    flash("Please log in as a brand to view your profile.", "error")
    return redirect(url_for('main.login'))

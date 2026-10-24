import os
import re
import secrets
from decimal import Decimal, InvalidOperation
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

MAX_PRODUCT_IMAGES = 8
MAX_PRODUCT_IMAGE_SIZE = 5 * 1024 * 1024
ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
PRODUCT_STATUSES = {'Available', 'Out of Stock', 'Discontinued'}
MAX_PRICE = Decimal('99999999.99')


def _upload_form_response(status_code=200):
    categories = Category.query.order_by(Category.category_name).all()
    colors = Color.query.order_by(Color.color_name).all()
    sizes = Size.query.order_by(Size.sort_order).all()
    return render_template(
        'vendor/upload.html',
        category=categories,
        colors=colors,
        sizes=sizes,
    ), status_code


def _parse_positive_price(value, field_name):
    try:
        price = Decimal(value.strip())
    except (AttributeError, InvalidOperation):
        raise ValueError(f'{field_name} must be a valid price.')
    if (
        not price.is_finite()
        or price <= 0
        or price > MAX_PRICE
        or price != price.quantize(Decimal('0.01'))
    ):
        raise ValueError(f'{field_name} must be greater than zero and have at most two decimal places.')
    return price


def _parse_positive_id(value, field_name):
    if not value or not re.fullmatch(r'[0-9]+', value.strip()):
        raise ValueError(f'{field_name} must be selected.')
    parsed_value = int(value)
    if parsed_value < 1 or parsed_value > 2147483647:
        raise ValueError(f'{field_name} must be selected.')
    return parsed_value


def _image_signature_matches(extension, header):
    return (
        (extension in {'.jpg', '.jpeg'} and header.startswith(b'\xff\xd8\xff'))
        or (extension == '.png' and header.startswith(b'\x89PNG\r\n\x1a\n'))
        or (
            extension == '.webp'
            and len(header) >= 12
            and header[:4] == b'RIFF'
            and header[8:12] == b'WEBP'
        )
    )


def _remove_uploaded_files(paths):
    for path in paths:
        try:
            os.remove(path)
        except FileNotFoundError:
            continue
        except OSError:
            current_app.logger.exception('Could not remove failed product upload %s.', path)


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
        product_name = (request.form.get('product_name') or '').strip()
        description = (request.form.get('description') or '').strip()
        status = request.form.get('status', 'Available')
        uploaded_files = [
            file for file in request.files.getlist('product_images')
            if file and file.filename
        ]
        uploaded_paths = []

        try:
            if not product_name or len(product_name) > 100:
                raise ValueError('Product name is required and must be 100 characters or fewer.')
            category_id = _parse_positive_id(request.form.get('category'), 'Category')
            if db.session.get(Category, category_id) is None:
                raise ValueError('Select an existing category.')
            base_price = _parse_positive_price(
                request.form.get('base_price'),
                'Base price',
            )
            if status not in PRODUCT_STATUSES:
                raise ValueError('Select a valid product status.')
            if len(uploaded_files) > MAX_PRODUCT_IMAGES:
                raise ValueError(f'Upload no more than {MAX_PRODUCT_IMAGES} product images.')

            image_color_ids = request.form.getlist('product_image_colors[]')
            if image_color_ids and len(image_color_ids) != len(uploaded_files):
                raise ValueError('Choose a color for each uploaded image or leave it unassigned.')

            validated_images = []
            for index, file in enumerate(uploaded_files):
                filename = secure_filename(file.filename)
                extension = os.path.splitext(filename)[1].lower()
                if not filename or extension not in ALLOWED_IMAGE_EXTENSIONS:
                    raise ValueError('Product images must be JPG, PNG, or WEBP files.')

                image_data = file.stream.read(MAX_PRODUCT_IMAGE_SIZE + 1)
                file.stream.seek(0)
                if len(image_data) > MAX_PRODUCT_IMAGE_SIZE:
                    raise ValueError('Each product image must be 5 MB or smaller.')
                if not image_data or not _image_signature_matches(extension, image_data[:12]):
                    raise ValueError('An uploaded file is not a valid JPG, PNG, or WEBP image.')

                color_value = image_color_ids[index].strip() if image_color_ids else ''
                color_id = None
                if color_value:
                    color_id = _parse_positive_id(color_value, 'Image color')
                    if db.session.get(Color, color_id) is None:
                        raise ValueError('Select an existing color for each product image.')
                validated_images.append((file, filename, color_id))

            variant_color_ids = request.form.getlist('variant_color[]')
            variant_size_ids = request.form.getlist('variant_size[]')
            variant_prices = request.form.getlist('variant_price[]')
            variant_stocks = request.form.getlist('variant_stock[]')
            variant_count = len(variant_color_ids)
            if (
                variant_count == 0
                or len(variant_size_ids) != variant_count
                or len(variant_prices) != variant_count
                or len(variant_stocks) != variant_count
            ):
                raise ValueError('Add at least one complete product variant.')

            validated_variants = []
            seen_variants = set()
            for color_value, size_value, price_value, stock_value in zip(
                variant_color_ids,
                variant_size_ids,
                variant_prices,
                variant_stocks,
            ):
                color_id = _parse_positive_id(color_value, 'Variant color')
                size_id = _parse_positive_id(size_value, 'Variant size')
                if (
                    db.session.get(Color, color_id) is None
                    or db.session.get(Size, size_id) is None
                ):
                    raise ValueError('Select an existing color and size for every variant.')

                variant_key = (color_id, size_id)
                if variant_key in seen_variants:
                    raise ValueError('Each color and size combination can only be added once.')
                seen_variants.add(variant_key)

                price = (
                    _parse_positive_price(price_value, 'Variant price')
                    if price_value.strip()
                    else base_price
                )
                if not re.fullmatch(r'[0-9]+', stock_value.strip()):
                    raise ValueError('Variant stock must be a whole number of zero or more.')
                stock = int(stock_value)
                if stock > 2147483647:
                    raise ValueError('Variant stock is too large.')
                validated_variants.append((color_id, size_id, price, stock))
        except ValueError as error:
            flash(str(error), 'error')
            return _upload_form_response(400)

        brand = db.session.get(Brand, brand_id)
        if brand is None:
            session.pop('brandonline', None)
            flash('Your brand account could not be found. Please log in again.', 'error')
            return redirect(url_for('main.login'))

        try:
            product = Product(
                product_name=product_name,
                brand_id=brand_id,
                category_id=category_id,
                price=base_price,
                description=description or None,
                status=status,
            )
            db.session.add(product)
            db.session.flush()

            upload_folder = os.path.join(current_app.root_path, 'static', 'media')
            os.makedirs(upload_folder, exist_ok=True)
            for file, filename, color_id in validated_images:
                unique_filename = f"{secrets.token_hex(8)}_{filename}"
                file_path = os.path.join(upload_folder, unique_filename)
                uploaded_paths.append(file_path)
                file.save(file_path)
                db.session.add(ProductImage(
                    product_id=product.product_id,
                    image=unique_filename,
                    color_id=color_id,
                ))

            for color_id, size_id, price, stock in validated_variants:
                db.session.add(ProductVariant(
                    productvariant_id=product.product_id,
                    color_id=color_id,
                    size_id=size_id,
                    price=price,
                    stock_quantity=stock,
                ))

            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            _remove_uploaded_files(uploaded_paths)
            current_app.logger.exception('Could not save uploaded product %s.', product_name)
            flash('The product could not be saved. Please try again.', 'error')
            return _upload_form_response(503)
        except OSError:
            db.session.rollback()
            _remove_uploaded_files(uploaded_paths)
            current_app.logger.exception('Could not store images for product %s.', product_name)
            flash('The product images could not be stored. Please try again.', 'error')
            return _upload_form_response(503)

        flash("Product uploaded successfully.", "success")
        return redirect(url_for('vendor.vendor_dash'))

    return _upload_form_response()


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

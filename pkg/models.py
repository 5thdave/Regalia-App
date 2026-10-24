from datetime import datetime
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()

class Admin(db.Model):
    __tablename__ = 'admins'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True,autoincrement=True)
    name = db.Column(db.String(100))
    gender = db.Column(db.Enum('Male', 'Female', 'Other', name='gender_enum'))
    email = db.Column(db.String(255), unique=True)
    dateofbirth = db.Column(db.Date)
    phone = db.Column(db.String(45))
    country = db.Column(db.String(45))
    address = db.Column(db.String(255))
    password = db.Column(db.String(255))
    time_created = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.Enum('Active', 'Inactive', 'Suspended', name='user_status_enum'),default="Active")
    # Relationships
    orders = db.relationship('Order', backref='user', lazy=True)
    payments = db.relationship('Payment', backref='user', lazy=True)
    reviews = db.relationship('Review', backref='user', lazy=True)
    wishlists = db.relationship('Wishlist', backref='user', lazy=True)
    favorite_brands = db.relationship(
        'FavoriteBrand', back_populates='user', cascade='all, delete-orphan', lazy=True
    )
class Brand(db.Model):
    __tablename__ = 'brand'
    brand_id = db.Column(db.Integer, primary_key=True,autoincrement=True)
    brand_name = db.Column(db.String(100))
    brand_email = db.Column(db.String(100), unique=True)
    brand_phone = db.Column(db.String(45))
    brand_desc = db.Column(db.Text)
    password = db.Column(db.String(255))
    # Relationships
    products = db.relationship('Product', backref='brand', lazy=True)
    payouts = db.relationship('Payout', backref='brand', lazy=True)
    favorites = db.relationship(
        'FavoriteBrand', back_populates='brand', cascade='all, delete-orphan', lazy=True
    )

class BrandLogo(db.Model):
    __tablename__ = 'brandlogo'
    logo_id = db.Column(db.Integer, primary_key=True,autoincrement=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brand.brand_id'))   
    logo = db.Column(db.String(500))
    

class FavoriteBrand(db.Model):
    __tablename__ = 'favorite_brands'
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brand.brand_id', ondelete='CASCADE'), primary_key=True)
    user = db.relationship('User', back_populates='favorite_brands')
    brand = db.relationship('Brand', back_populates='favorites')


class Category(db.Model):
    __tablename__ = 'category'
    category_id = db.Column(db.Integer, primary_key=True,autoincrement=True)
    category_name = db.Column(db.String(100))
    description = db.Column(db.Text)
    # Relationships
    products = db.relationship('Product', backref='category', lazy=True)
class Product(db.Model):
    __tablename__ = 'products'
    product_id = db.Column(db.Integer, primary_key=True,autoincrement=True)
    product_name = db.Column(db.String(100))
    brand_id = db.Column(db.Integer, db.ForeignKey('brand.brand_id'))
    category_id = db.Column(db.Integer, db.ForeignKey('category.category_id'))
    price = db.Column(db.Numeric(10, 2))
    description = db.Column(db.Text)
    status = db.Column(db.Enum('Available', 'Out of Stock', 'Discontinued', name='product_status_enum'))
    time_created = db.Column(db.DateTime, default=datetime.utcnow)
    # Relationships
    images = db.relationship('ProductImage', backref='product', lazy=True)
    variants = db.relationship('ProductVariant', backref='product', lazy=True)
    reviews = db.relationship('Review', backref='product', lazy=True)
    wishlists = db.relationship('Wishlist', backref='product', lazy=True)
    order_items = db.relationship('OrderItem', backref='product', lazy=True)

class Color(db.Model):
    __tablename__ = 'colors'
    color_id = db.Column(db.Integer, primary_key=True,autoincrement=True)
    color_name = db.Column(db.String(100), nullable=False, unique=True)
    hex_code = db.Column(db.String(10), nullable=False, default='#111212')
    # Relationships
    variants = db.relationship('ProductVariant', backref='color', lazy=True)
    images = db.relationship('ProductImage', backref='color', lazy=True)

class Size(db.Model):
    __tablename__ = 'sizes'
    size_id = db.Column(db.Integer, primary_key=True,autoincrement=True)
    size_code = db.Column(db.String(20), nullable=False)
    size_name = db.Column(db.String(50))
    sort_order = db.Column(db.Integer, default=0)
    # Relationships
    variants = db.relationship('ProductVariant', backref='size', lazy=True)

class ProductImage(db.Model):
    __tablename__ = 'product_images'
    image_id = db.Column(db.Integer, primary_key=True,autoincrement=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.product_id'))
    color_id = db.Column(db.Integer, db.ForeignKey('colors.color_id'), nullable=True)
    # size_id = db.Column(db.Integer, db.ForeignKey('size.size_id'), nullable=True)
    # productvariant_id = db.Column(db.Integer, db.ForeignKey('product_variants.variant_id'))
    image = db.Column(db.String(500))

class ProductVariant(db.Model):
    __tablename__ = 'product_variants'
    variant_id = db.Column(db.Integer, primary_key=True,autoincrement=True)
    productvariant_id = db.Column(db.Integer, db.ForeignKey('products.product_id'))
    stock_quantity = db.Column(db.Integer, default=0)
    price = db.Column(db.Numeric(10, 2))
    color_id = db.Column(db.Integer, db.ForeignKey('colors.color_id'), nullable=True)
    size_id = db.Column(db.Integer, db.ForeignKey('sizes.size_id'), nullable=True)
    # Relationships
    order_items = db.relationship('OrderItem', backref='variant', lazy=True)
    
class Order(db.Model):
    __tablename__ = 'orders'
    order_id = db.Column(db.Integer, primary_key=True,autoincrement=True)
    orderuser_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    order_amt = db.Column(db.Numeric(10, 2))
    order_date = db.Column(db.DateTime, default=datetime.utcnow)
    order_status = db.Column(db.Enum('Pending', 'Processing', 'Shipped', 'Delivered', 'Cancelled', name='order_status_enum'))
    order_update_date = db.Column(db.DateTime, onupdate=datetime.utcnow)
    # Relationships
    items = db.relationship('OrderItem', backref='order', lazy=True)
    payments = db.relationship('Payment', backref='order', lazy=True)
    payouts = db.relationship('Payout', backref='order', lazy=True)
 
class OrderItem(db.Model):
    __tablename__ = 'order_items'
    orderitem_id = db.Column(db.Integer, primary_key=True,autoincrement=True)
    itemorder_id = db.Column(db.Integer, db.ForeignKey('orders.order_id'))
    itemproduct_id = db.Column(db.Integer, db.ForeignKey('products.product_id'))
    itemvariant_id = db.Column(db.Integer, db.ForeignKey('product_variants.variant_id'))
    quantity = db.Column(db.Integer)
    unit_price = db.Column(db.Numeric(10, 2))
    # Relationships
    reviews = db.relationship('Review', backref='order_item', lazy=True)
    
class Payment(db.Model):
    __tablename__ = 'payment'
    payment_id = db.Column(db.Integer, primary_key=True,autoincrement=True)
    paymentorder_id = db.Column(db.Integer, db.ForeignKey('orders.order_id'))
    paymentuser_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    payment_method = db.Column(db.String(45))
    transaction_ref = db.Column(db.String(100))
    amount = db.Column(db.Numeric(10, 2))
    currency = db.Column(db.String(3))
    status = db.Column(db.Enum('Pending', 'Completed', 'Failed', 'Refunded', name='payment_status_enum'))
    payment_type = db.Column(db.Enum('Card', 'Bank Transfer', 'PayPal', name='payment_type_enum'))
    time_created = db.Column(db.DateTime, default=datetime.utcnow)
    payment_gateway = db.Column(db.String(45))
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    
class Review(db.Model):
    __tablename__ = 'review'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'product_id', name='uq_review_user_product'),
    )
    review_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    comment = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    product_id = db.Column(db.Integer, db.ForeignKey('products.product_id'))
    rating = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    order_item_id = db.Column(db.Integer, db.ForeignKey('order_items.orderitem_id'))
class Wishlist(db.Model):
    __tablename__ = 'wishlist'
    wishlist_id = db.Column(db.Integer, primary_key=True,autoincrement=True)
    wishlistuser_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    wishlistproduct_id = db.Column(db.Integer, db.ForeignKey('products.product_id'))
    time_added = db.Column(db.DateTime, default=datetime.utcnow)
    
class Payout(db.Model):
    __tablename__ = 'payouts'
    payout_id = db.Column(db.Integer, primary_key=True,autoincrement=True)
    payoutbrand_id = db.Column(db.Integer, db.ForeignKey('brand.brand_id'))
    payoutorder_id = db.Column(db.Integer, db.ForeignKey('orders.order_id'))
    gross_amount = db.Column(db.Numeric(10, 2))
    commission_rate = db.Column(db.Numeric(10, 2))
    commission_amount = db.Column(db.Numeric(10, 2))
    net_amount = db.Column(db.Numeric(10, 2))
    status = db.Column(db.Enum('Pending', 'Processed', 'Failed', name='payout_status_enum'))
    paid_at = db.Column(db.DateTime)
    payout_reference = db.Column(db.String(100))
    time_created = db.Column(db.DateTime, default=datetime.utcnow)


class NewsletterSubscriber(db.Model):
    __tablename__ = 'newsletter_subscribers'
    subscriber_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.String(254), nullable=False, unique=True, index=True)
    subscribed_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

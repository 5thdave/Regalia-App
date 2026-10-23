from flask import Blueprint, flash, render_template, request, redirect, url_for, session
from pkg.models import db, Admin, Brand, User, Category, Color
from werkzeug.security import check_password_hash


admin = Blueprint('admin', __name__, template_folder='templates', static_folder='static')


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


@admin.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('admin.login'))


@admin.route('/')
def admin_dashboard():
    brands = Brand.query.all()
    
    return render_template('admin/index.html', brands = brands)

@admin.route('/brands')
def brands():
    brands = Brand.query.all()
    return render_template('admin/brands.html', brands = brands)

@admin.route('/orders')
def orders():
    return render_template('admin/orders.html')

@admin.route('/categories', methods = ['GET','POST'])
def categories():
    if request.method == 'POST':
        name = request.form.get('category_name')
        desc = request.form.get('description')
        cat = Category(category_name=name,description=desc)
        db.session.add(cat)
        db.session.commit()
        return redirect(url_for('admin.categories'))
        
    category = Category.query.all()
    
    return render_template('admin/categories.html' , category = category)

@admin.route('/colors', methods = ['GET', 'POST'])
def colors():
    if request.method == 'POST':
        name = request.form.get('color_name', '').strip()
        hex_code = request.form.get('hex_code', '').strip()
        if name and hex_code:
            existing = Color.query.filter(Color.color_name.ilike(name)).first()
            if not existing:
                col = Color(color_name=name, hex_code=hex_code)
                db.session.add(col)
                db.session.commit()
        return redirect(url_for('admin.colors'))

    all_colors = Color.query.order_by(Color.color_name).all()
    return render_template('admin/colors.html', colors=all_colors)

@admin.route('/colors/delete/<int:color_id>', methods=['POST', 'GET'])
def delete_color(color_id):
    color = Color.query.get_or_404(color_id)
    if not color.variants:
        db.session.delete(color)
        db.session.commit()
    return redirect(url_for('admin.colors'))

@admin.route('/payouts')
def payouts():
    return render_template('admin/payouts.html')

@admin.route('/reviews')
def reviews():
    return render_template('admin/reviews.html')

@admin.route('/users')
def users():
    users = User.query.all()
    return render_template('admin/users.html' , users=users)



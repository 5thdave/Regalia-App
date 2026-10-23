from flask import Flask
from pkg.config import DevelopmentConfig
from pkg.user.routes import user
from pkg.vendor.routes import vendor
from pkg.admin.routes import admin
from pkg.main.routes import main
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect


csrf = CSRFProtect()


def create_app():   
    from pkg.models import db
    app = Flask(__name__)
    # CORS(app, resources={
    #     r"/api/v1/.*": {
    #         "origins": ["*"],
    #         "methods": ["GET", "POST", "OPTIONS"],
    #         "allow_headers": ["Content-Type", "Authorization"]
    #     }
    # })
    
    app.config.from_object(DevelopmentConfig)
    
    app.register_blueprint(main)
    app.register_blueprint(user,url_prefix='/user')
    app.register_blueprint(admin,url_prefix='/admin')
    app.register_blueprint(vendor,url_prefix='/vendor')
    
    db.init_app(app)
    migrate = Migrate(app,db)
    csrf.init_app(app)

    with app.app_context():
        from pkg.seed import seed_defaults
        seed_defaults()

    return app

app = create_app()

from flask_mail import Mail
from flask_wtf.csrf import CSRFProtect


csrf = CSRFProtect()
mail = Mail()

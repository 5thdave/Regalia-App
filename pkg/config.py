import codecs
import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / '.env')

# Ensure utf8mb4 encoding alias exists for MySQL connector on newer Python versions
try:
    codecs.lookup('utf8mb4')
except LookupError:
    codecs.register(lambda name: codecs.lookup('utf-8') if name.lower() in ('utf8mb4', 'utf_8_mb4') else None)


class GeneralConfig:
    APP_NAME = 'regalia'
    SECRET_KEY = os.getenv('SECRET_KEY')
    CURRENCY = 'NGN'
    CURRENCY_SYMBOL = '₦'


class DevelopmentConfig(GeneralConfig):
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024
    MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.getenv('MAIL_PORT', '465'))
    MAIL_USERNAME = os.getenv('MAIL_USERNAME')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')
    MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', 'false').strip().lower() == 'true'
    MAIL_USE_SSL = os.getenv('MAIL_USE_SSL', 'true').strip().lower() == 'true'
    MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER') or MAIL_USERNAME

import os
from dotenv import load_dotenv

load_dotenv()


class GeneralConfig:
    APP_NAME = 'regalia'
    SECRET_KEY = os.getenv('SECRET_KEY')
    CURRENCY = 'NGN'
    CURRENCY_SYMBOL = '₦'


class DevelopmentConfig(GeneralConfig):
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')
    
import os
from dotenv import load_dotenv

load_dotenv()


class GeneralConfig:
    APP_NAME = 'regalia'
    SECRET_KEY = os.getenv('SECRET_KEY')


class DevelopmentConfig(GeneralConfig):
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')
    
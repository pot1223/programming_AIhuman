import os
from pathlib import Path
from dotenv import load_dotenv


basedir = Path(__file__).parent.parent
load_dotenv(basedir / '.env')

class BaseConfig:
    SECRET_KEY = os.getenv("SECRET_KEY", "sodalabsecretss")
    COMMON_PASSWORD = os.getenv("COMMON_PASSWORD")


class DevConfig(BaseConfig):
    DB_USER = os.getenv('DB_USER')
    DB_PASSWORD = os.getenv('DB_PASSWORD')
    DB_HOST = os.getenv('DB_HOST')
    DB_NAME = os.getenv('DB_NAME')
    DB_PORT = os.getenv('DB_PORT')

    SQLALCHEMY_DATABASE_URI = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?sslmode=require"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False


config = {
    "dev": DevConfig
}
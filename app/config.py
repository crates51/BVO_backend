import os

MYSQL_DATABASE = os.environ["MYSQL_DATABASE"]
MYSQL_USER = os.environ["MYSQL_USER"]
MYSQL_PASSWORD = os.environ["MYSQL_PASSWORD"]
MYSQL_HOST = os.environ["MYSQL_HOST"]
MYSQL_URL = f"mysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}/{MYSQL_DATABASE}"


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "sdfl43kDKr4!djas*d43oj3rdfd")
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = MYSQL_URL
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
        "pool_size": 100,
    }
    REDIS_URL = os.environ.get("REDIS_URL") or "redis://"


class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = True


class ProductionConfig(Config):
    DEBUG = False


config_by_name = dict(dev=DevelopmentConfig, prod=ProductionConfig)

key = Config.SECRET_KEY

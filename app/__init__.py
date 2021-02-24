# app/__init__.py

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from .config import config_by_name
from redis import Redis
import rq
from app.middleware import auth_middleware

db = SQLAlchemy()


def create_app(config_name):
    app = Flask(__name__)
    app.wsgi_app = auth_middleware(app.wsgi_app)
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config.from_object(config_by_name[config_name])
    app.redis = Redis.from_url(app.config["REDIS_URL"])
    app.task_queue = rq.Queue("olt-tasks", connection=app.redis, job_timeout=600)
    db.init_app(app)
    return app

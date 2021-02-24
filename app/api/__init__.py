# app/main/__init__.py

from flask import Blueprint
from flask_restplus import Api

# from .controller.olt_controller import api as olt_ns
from .controller.products_controller import api as product_ns


blueprint = Blueprint("api", __name__)

api = Api(
    blueprint,
    title="BVO-Backend API",
    version="1.0",
    description="An api for BVO management",
)

api.add_namespace(product_ns, path="/Product")

# from flask import request
from flask import request
from flask_restplus import Resource
from ..util.dto import ProductsDTO
from ..service.products_service import get_all_products, save_new_product

api = ProductsDTO.api
# _olt = OLTDto.olt


@api.route("/")
class ProductsGet(Resource):
    @api.response(201, "Products successfully received.")
    # @api.expect(_olt, validate=True)
    def get(self):
        """Receive all products """
        # data = request.json
        # return list_all_products(data=data)
        return get_all_products()

    @api.response(201, "Product successfully created.")
    @api.response(409, "Product already exists.")
    @api.response(417, "Product creation Failled.")
    # @api.expect(_olt, validate=True)
    def post(self):
        """Save a new Product """
        data = request.json
        return save_new_product(data=data)

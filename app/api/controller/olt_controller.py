# from flask import request
# from flask_restplus import Resource
# from ..util.dto import OLTDto
# from ..service.products_service import list_all_products

# api = OLTDto.api
# _olt = OLTDto.olt


# @api.route("/")
# class OLTList(Resource):
#     @api.response(201, "OLT successfully created.")
#     @api.response(409, "OLT already exists.")
#     @api.response(417, "OLT creation Failled.")
#     @api.expect(_olt, validate=True)
#     def post(self):
#         """Creates a new OLT """
#         data = request.json
#         return list_all_products(data=data)

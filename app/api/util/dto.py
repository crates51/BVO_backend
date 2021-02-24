from flask_restplus import Namespace, fields


class ProductsDTO:
    api = Namespace("OLT", description="Products related operations")
    product = api.model(
        "Product",
        {
            "id": fields.Integer(required=False, description="OLT id"),
            "name": fields.String(required=True, description="Product Name"),
            "category": fields.String(required=False, description="Product Category"),
            "description": fields.String(
                required=True, description="Product Description"
            ),
            "price": fields.Integer(required=False, description="Product Price"),
            "quantity": fields.Integer(
                required=False, description="Product Quantity left"
            ),
        },
    )

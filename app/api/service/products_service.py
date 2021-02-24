import logging

# from ...models.olt import (
# db,
# OLT,
# DBAProfiles,
# TargetFwVersions,
# OLTVlans,
# OLTSlots,
# VoipProfiles,
# DasanTrafficProfiles,
# DasanTPServices,
# DasanTPPorts,
# DasanTPVlans,
# DasanONTProfiles,
# IPPool,
# )

from app.api.util.helpers import return_success, return_error, safe_commit
from app.api.util.dto import ProductsDTO
from ...models.product import Product, db
from flask_restplus import marshal

# from ...models.ont import ONT
# from ...models.ont import *
# from ...models.interfaces import Interfaces
# import datetime
# from flask import current_app

# from app.libs.dasan_reader import DasanReader
# import ipaddress
# import sqlalchemy.exc
# from app.api.util.dto import ONTDto, OLTDto, InterfacesDto, TasksDto
# import traceback


libLogger = logging.getLogger("main." + __name__)
_product = ProductsDTO.product


def get_all_products():
    all_products = Product.query.all()
    return return_success(marshal(all_products, _product), 201)


def save_new_product(data):
    found_product = Product.query.filter_by(name=data["name"]).first()
    if found_product:
        return return_error(
            f"Produsul {data['name']} exista deja in baza de date !", 400
        )

    new_product = Product(
        name=data["name"], category=data["category"], price=data["price"]
    )
    db.session.add(new_product)

    commit_result = safe_commit(
        success_msg=f"Produsul {new_product.name} a fost salvat cu succes in baza de date",
        success_code=201,
        error_msg=f"Produsul {new_product.name} nu a putut fi salvat in baza de date",
        error_code=404,
    )

    if commit_result[1] == 201:
        libLogger.debug(commit_result[0])
        return commit_result
    else:
        libLogger.error(commit_result[0])
        return commit_result

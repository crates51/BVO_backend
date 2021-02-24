import logging
from ...models.olt import (
    db,
    OLT,
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
)

# from ...models.ont import ONT
# from ...models.ont import *
# from ...models.interfaces import Interfaces
# import datetime
# from flask import current_app

# from app.libs.dasan_reader import DasanReader
# import ipaddress
# import sqlalchemy.exc
# from app.api.util.dto import ONTDto, OLTDto, InterfacesDto, TasksDto
# from flask_restplus import marshal
# import traceback


libLogger = logging.getLogger("main." + __name__)
# _olt = OLTDto.olt
# _ont = ONTDto.ont
# _dba = OLTDto.dba


def return_success(msg, return_code):
    response_object = {"status": "Success", "data": msg}
    return response_object, return_code


def return_error(msg, return_code):
    response_object = {"status": "Fail", "data": msg}
    return response_object, return_code


def safe_commit(
    success_msg="Succesfully saved to DB",
    success_code=201,
    error_msg="Error saving object to database",
    error_code=404,
):
    try:
        db.session.commit()
        return return_success(success_msg, success_code)
    except Exception as e:
        db.session.rollback()
        libLogger.exception(f"{error_msg}. Error is:\n{e}")
        return return_error(error_msg, error_code)


def save_new_olt(data):
    OLTByHostname = OLT.query.filter_by(hostname=data["hostname"]).first()
    OLTByIP = OLT.query.filter_by(ip=data["ip"]).first()
    if not OLTByHostname and not OLTByIP:
        new = OLT(
            hostname=data["hostname"],
            ip=data["ip"],
            device_model_id=data["device_model_id"],
            branch=data["branch"],
            snmpv2_community=data["snmpv2_community"],
            snmpv2_write=data["snmpv2_write"],
            username=data["username"],
            password=data["password"],
            status=data["status"],
        )
        if "fw_version" in data.keys():
            new.fw_version = (data["fw_version"],)
        db.session.add(new)
        return safe_commit(
            success_msg=f"OLT-ul {new.hostname} a fost salvat cu succes in baza de date",
            success_code=201,
            error_msg=f"Error saving  OLT {new.hostname} to database",
            error_code=404,
        )
    else:
        libLogger.error("OLT hostname or IP address already exists")
        return return_error(
            "Numele OLT-ului sau adresa IP exista deja in baza de date", 409
        )

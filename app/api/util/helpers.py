from ... import db
import logging


libLogger = logging.getLogger(__name__)


def return_success(msg, return_code):
    response_object = {"status": "success", "data": msg}
    return response_object, return_code


def return_error(msg, return_code):
    response_object = {"status": "fail", "data": msg}
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

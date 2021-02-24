import traceback
import logging
import requests
import json
from os import getenv

libLogger = logging.getLogger("main." + __name__)
ENV_TYPE = getenv('ENV_TYPE') or 'dev'
if ENV_TYPE != 'dev':
    # we use the first account specified
    AA = json.loads(getenv("AUTHORIZED_ACCOUNTS"))[0]
    auth=requests.auth.HTTPBasicAuth(AA['username'], AA['password'])
else:
    auth = None

def check_olt_status():
    try:
        if ENV_TYPE != 'prod':
            r = requests.get("http://localhost:6001/OLT/check_status_all", timeout=10)
        else:
            r = requests.get("http://10.253.51.9:6001/OLT/check_status_all", auth=auth, timeout=10)
    except Exception as e:
        libLogger.error(f"Error on check_status_all: {e}")
        libLogger.debug(traceback.format_exc())
       
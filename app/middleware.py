
from werkzeug.wrappers import Request, Response, ResponseStream
import os
import logging
import json


libLogger = logging.getLogger("main." + __name__)
AUTHORIZED_ACCOUNTS = os.environ["AUTHORIZED_ACCOUNTS"] or None


class auth_middleware():

    def __init__(self, app):
        self.app = app
        self.ENV_TYPE = os.getenv('ENV_TYPE') or 'dev'
        if self.ENV_TYPE != 'dev':
            self.AA = json.loads(AUTHORIZED_ACCOUNTS)

    def __call__(self, environ, start_response):
        # we only need auth for production env, ignore in dev env
        if self.ENV_TYPE == 'dev':
            return self.app(environ, start_response)
        request = Request(environ)
        if getattr(request,'authorization'):
            username = request.authorization['username']
            password = request.authorization['password']
            for account in self.AA:
                if username == account['username'] and password == account['password']:
                    return self.app(environ, start_response)
        libLogger.error(f'Authorization failed from {request.remote_addr} on {request.url}')
        response_object = {
            'status': 'error',
            'data': 'Authorization failed'
        }
        res = Response(json.dumps(response_object), mimetype= 'text/plain', content_type='application/json', status=401)
        return res(environ, start_response)

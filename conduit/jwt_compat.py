# -*- coding: utf-8 -*-
"""Keep Flask-JWT-Extended 3.x request handling on top of Flask-JWT-Extended 4.x.

API clients depend on the 3.x responses, so the Authorization header parsing, the token type
check and the ``jwt_optional`` fallback are ported verbatim from Flask-JWT-Extended 3.25.1.
"""
from contextvars import ContextVar
from functools import wraps
from re import split

from flask import request
from flask_jwt_extended import verify_jwt_in_request, view_decorators
from flask_jwt_extended.config import config
from flask_jwt_extended.exceptions import (InvalidHeaderError, JWTDecodeError,
                                           NoAuthorizationError, WrongTokenError)

_optional = ContextVar('conduit_jwt_optional', default=False)


def _decode_jwt_from_headers():
    header_name = config.header_name
    header_type = config.header_type

    auth_header = request.headers.get(header_name, None)
    if not auth_header:
        raise NoAuthorizationError("Missing {} Header".format(header_name))

    if header_type:
        field_values = split(r',\s*', auth_header)
        jwt_header = [s for s in field_values if s.split()[0] == header_type]
        if len(jwt_header) < 1 or len(jwt_header[0].split()) != 2:
            msg = "Bad {} header. Expected value '{} <JWT>'".format(header_name, header_type)
            if _optional.get():
                # 3.x jwt_optional treated an invalid header as no token at all.
                raise NoAuthorizationError(msg)
            raise InvalidHeaderError(msg)
        jwt_header = jwt_header[0]
    else:
        jwt_header = auth_header

    parts = jwt_header.split()
    if not header_type:
        if len(parts) != 1:
            msg = "Bad {} header. Expected value '<JWT>'".format(header_name)
            if _optional.get():
                raise NoAuthorizationError(msg)
            raise InvalidHeaderError(msg)
        encoded_token = parts[0]
    else:
        encoded_token = parts[1]

    return encoded_token, None


def _verify_token_type(decoded_token, refresh):
    if decoded_token['type'] not in ('refresh', 'access'):
        raise JWTDecodeError("Missing or invalid claim: type")
    expected_type = 'refresh' if refresh else 'access'
    if decoded_token['type'] != expected_type:
        raise WrongTokenError('Only {} tokens are allowed'.format(expected_type))


assert hasattr(view_decorators, '_decode_jwt_from_headers')
assert hasattr(view_decorators, 'verify_token_type')
view_decorators._decode_jwt_from_headers = _decode_jwt_from_headers
view_decorators.verify_token_type = _verify_token_type


def jwt_optional(fn):
    """Flask-JWT-Extended 3.x ``jwt_optional``: a missing or invalid header means anonymous."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        reset = _optional.set(True)
        try:
            verify_jwt_in_request(optional=True)
        finally:
            _optional.reset(reset)
        return fn(*args, **kwargs)
    return wrapper

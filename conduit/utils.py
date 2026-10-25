# -*- coding: utf-8 -*-
"""Helper utilities and decorators."""
from flask import current_app

from conduit.user.models import User  # noqa


def jwt_identity(jwt_header, jwt_data):
    return User.get_by_id(jwt_data[current_app.config['JWT_IDENTITY_CLAIM']])


def identity_loader(user):
    return user.id

# -*- coding: utf-8 -*-
"""Application configuration."""
import os
from datetime import timedelta


def database_url_from_env(default='postgresql://localhost/example'):
    """Read ``DATABASE_URL``, accepting Heroku's ``postgres://`` scheme (rejected by SQLAlchemy >= 1.4)."""
    url = os.environ.get('DATABASE_URL', default)
    if url.startswith('postgres://'):
        url = 'postgresql://' + url[len('postgres://'):]
    return url


class Config(object):
    """Base configuration."""

    SECRET_KEY = os.environ.get('CONDUIT_SECRET', 'secret-key')  # TODO: Change me
    APP_DIR = os.path.abspath(os.path.dirname(__file__))  # This directory
    PROJECT_ROOT = os.path.abspath(os.path.join(APP_DIR, os.pardir))
    BCRYPT_LOG_ROUNDS = 13
    DEBUG_TB_INTERCEPT_REDIRECTS = False
    CACHE_TYPE = 'simple'  # Can be "memcached", "redis", etc.
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_AUTH_USERNAME_KEY = 'email'
    JWT_AUTH_HEADER_PREFIX = 'Token'
    CORS_ORIGIN_WHITELIST = [
        'http://0.0.0.0:4100',
        'http://localhost:4100',
        'http://0.0.0.0:8000',
        'http://localhost:8000',
        'http://0.0.0.0:4200',
        'http://localhost:4200',
        'http://0.0.0.0:4000',
        'http://localhost:4000',
    ]
    JWT_HEADER_TYPE = 'Token'
    # Keep the Flask-JWT-Extended 3 claim name (4.x defaults to 'sub') so tokens issued before the
    # upgrade stay valid and integer user ids don't trip PyJWT's "sub must be a string" check.
    JWT_IDENTITY_CLAIM = 'identity'
    JWT_COOKIE_CSRF_PROTECT = False


class ProdConfig(Config):
    """Production configuration."""

    ENV = 'prod'
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = database_url_from_env()


class DevConfig(Config):
    """Development configuration."""

    ENV = 'dev'
    DEBUG = True
    DB_NAME = 'dev.db'
    # Put the db file in project root
    DB_PATH = os.path.join(Config.PROJECT_ROOT, DB_NAME)
    SQLALCHEMY_DATABASE_URI = 'sqlite:///{0}'.format(DB_PATH)
    CACHE_TYPE = 'simple'  # Can be "memcached", "redis", etc.
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(10 ** 6)


class TestConfig(Config):
    """Test configuration."""

    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite://'
    # For faster tests; needs at least 4 to avoid "ValueError: Invalid rounds"
    BCRYPT_LOG_ROUNDS = 4
    # Fixed values so JWT-dependent oracle tests are reproducible (docs/ORACLE.md).
    SECRET_KEY = 'conduit-oracle-test-secret-key'
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=15)

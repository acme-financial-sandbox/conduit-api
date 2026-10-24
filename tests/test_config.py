# -*- coding: utf-8 -*-
"""Test configs."""
from conduit.app import create_app
from conduit.settings import DevConfig, ProdConfig


def test_production_config():
    """Production config."""
    app = create_app(ProdConfig)
    assert app.config['ENV'] == 'prod'
    assert not app.config['DEBUG']


def test_dev_config():
    """Development config."""
    app = create_app(DevConfig)
    assert app.config['ENV'] == 'dev'
    assert app.config['DEBUG']


def test_test_config():
    """Test config (the oracle baseline config)."""
    from datetime import timedelta
    from conduit.settings import TestConfig
    app = create_app(TestConfig)
    assert app.config['TESTING']
    assert app.config['DEBUG']
    assert app.config['SQLALCHEMY_DATABASE_URI'] == 'sqlite://'
    assert app.config['BCRYPT_LOG_ROUNDS'] == 4
    assert app.config['SECRET_KEY'] == 'conduit-oracle-test-secret-key'
    assert app.config['JWT_ACCESS_TOKEN_EXPIRES'] == timedelta(minutes=15)
    assert app.config['JWT_HEADER_TYPE'] == 'Token'


def test_app_fixture_always_uses_test_config(app, monkeypatch):
    """The ``app`` fixture is TestConfig/in-memory SQLite regardless of FLASK_DEBUG."""
    from conduit.settings import TestConfig
    assert app.config['TESTING']
    assert app.config['SQLALCHEMY_DATABASE_URI'] == 'sqlite://'
    assert app.config['SECRET_KEY'] == TestConfig.SECRET_KEY
    for flag in ('0', '1'):
        monkeypatch.setenv('FLASK_DEBUG', flag)
        fresh = create_app(TestConfig)
        assert fresh.config['TESTING']
        assert fresh.config['SQLALCHEMY_DATABASE_URI'] == 'sqlite://'


def test_database_url_from_env_default(monkeypatch):
    from conduit.settings import database_url_from_env
    monkeypatch.delenv('DATABASE_URL', raising=False)
    assert database_url_from_env() == 'postgresql://localhost/example'


def test_database_url_from_env_rewrites_heroku_scheme(monkeypatch):
    from conduit.settings import database_url_from_env
    monkeypatch.setenv('DATABASE_URL', 'postgres://u:p@host:5432/db')
    assert database_url_from_env() == 'postgresql://u:p@host:5432/db'
    monkeypatch.setenv('DATABASE_URL', 'postgresql://u:p@host:5432/db')
    assert database_url_from_env() == 'postgresql://u:p@host:5432/db'

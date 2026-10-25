# -*- coding: utf-8 -*-
"""Defines fixtures available to all tests."""

import pytest
from webtest import TestApp

from conduit.app import create_app
from conduit.database import db as _db
from conduit.settings import TestConfig
from conduit.profile.models import UserProfile


from .factories import UserFactory
from .oracle_helpers import register


@pytest.fixture(scope='function')
def app():
    """An application for the tests."""
    _app = create_app(TestConfig)

    with _app.app_context():
        _db.create_all()

    ctx = _app.test_request_context()
    ctx.push()

    yield _app

    ctx.pop()


@pytest.fixture(scope='function')
def testapp(app):
    """A Webtest app."""
    return TestApp(app)


@pytest.fixture(scope='function')
def db(app):
    """A database for the tests."""
    _db.app = app
    with app.app_context():
        _db.create_all()

    yield _db

    # Explicitly close DB connection
    _db.session.close()
    _db.drop_all()


@pytest.fixture
def user(db):
    """A user for the tests."""
    class User():
        def get(self):
            muser = UserFactory(password='myprecious')
            UserProfile(muser).save()
            db.session.commit()
            return muser
    return User()


@pytest.fixture
def alice(testapp, db):
    """Auth token for a user registered over HTTP."""
    return register(testapp, 'alice')


@pytest.fixture
def bob(testapp, db):
    """Auth token for a second user registered over HTTP."""
    return register(testapp, 'bob')


@pytest.fixture
def raises_unhandled(app):
    """Unhandled exceptions propagate under TestConfig; don't leave their request context pushed."""
    app.config['PRESERVE_CONTEXT_ON_EXCEPTION'] = False


@pytest.fixture
def no_propagate(app, raises_unhandled):
    """Let Flask turn unhandled exceptions into the 500 response production users see."""
    app.config['PROPAGATE_EXCEPTIONS'] = False

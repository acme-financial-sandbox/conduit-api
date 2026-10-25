# coding: utf-8
"""Oracle characterization tests for ``update_user``, registration conflicts and JWT edge cases."""
import datetime as dt

import jwt
import pytest
from flask_jwt_extended import create_access_token, create_refresh_token
from sqlalchemy.exc import IntegrityError

from conduit.exceptions import USER_ALREADY_REGISTERED, USER_NOT_FOUND
from conduit.profile.models import UserProfile
from conduit.settings import TestConfig
from conduit.user.models import User

from .oracle_helpers import login, send

SERVER_ERROR_HTML = '<title>500 Internal Server Error</title>'


def update(testapp, token, **fields):
    return send(testapp, 'PUT', '/api/user', {'user': fields}, token=token)


def login_resp(testapp, email, password):
    return send(testapp, 'POST', '/api/users/login', {'user': {'email': email, 'password': password}})


def get_user(testapp, token):
    return send(testapp, 'GET', '/api/user', token=token)


class TestUpdateUser:

    def test_envelope_and_fields(self, testapp, alice):
        resp = update(testapp, alice, username='alice2', email='alice2@example.com', bio='bio',
                      image='http://img.example.com/a.png')
        assert resp.status_int == 200
        assert list(resp.json) == ['user']
        user = resp.json['user']
        assert (user['username'], user['email'], user['bio'], user['image']) == (
            'alice2', 'alice2@example.com', 'bio', 'http://img.example.com/a.png')
        assert login_resp(testapp, 'alice2@example.com', 'secret').status_int == 200
        assert login_resp(testapp, 'alice@example.com', 'secret').status_int == 404

    def test_password_change(self, testapp, alice):
        assert update(testapp, alice, password='new-password').status_int == 200
        resp = login_resp(testapp, 'alice@example.com', 'secret')
        assert resp.status_int == 404
        assert resp.json == USER_NOT_FOUND['message']
        assert login_resp(testapp, 'alice@example.com', 'new-password').status_int == 200

    def test_empty_password_is_ignored(self, testapp, alice):
        assert update(testapp, alice, password='').status_int == 200
        assert login_resp(testapp, 'alice@example.com', 'secret').status_int == 200

    def test_empty_update_is_noop(self, testapp, alice):
        resp = update(testapp, alice)
        assert resp.status_int == 200
        assert resp.json['user']['username'] == 'alice'

    @pytest.mark.parametrize('value', ['', None])
    def test_empty_image_keeps_previous(self, testapp, alice, value):
        update(testapp, alice, image='http://img.example.com/a.png')
        resp = update(testapp, alice, image=value)
        assert resp.json['user']['image'] == 'http://img.example.com/a.png'

    @pytest.mark.parametrize('value', ['', None])
    def test_empty_email_keeps_previous(self, testapp, alice, value):
        resp = update(testapp, alice, email=value)
        assert resp.status_int == 200
        assert resp.json['user']['email'] == 'alice@example.com'

    def test_empty_bio_is_stored(self, testapp, alice):
        update(testapp, alice, bio='something')
        assert update(testapp, alice, bio='').json['user']['bio'] == ''

    # ORACLE: encodes current (buggy) behavior — revisit after upgrade
    @pytest.mark.oracle_known_bug
    def test_response_token_is_empty(self, testapp, alice):
        """The PUT response carries the ``User.token`` class default instead of a usable token."""
        assert update(testapp, alice, bio='x').json['user']['token'] == ''

    # ORACLE: encodes current (buggy) behavior — revisit after upgrade
    @pytest.mark.oracle_known_bug
    def test_updated_at_is_not_bumped(self, testapp, alice):
        before = login_resp(testapp, 'alice@example.com', 'secret').json['user']['updatedAt']
        after = update(testapp, alice, bio='changed').json['user']['updatedAt']
        assert after == before

    # ORACLE: encodes current (buggy) behavior — revisit after upgrade
    @pytest.mark.oracle_known_bug
    def test_sending_updated_at_resets_it_to_created_at(self, testapp, alice):
        user = update(testapp, alice, updatedAt='2000-01-01T00:00:00').json['user']
        assert user['updatedAt'] == user['createdAt']

    def test_requires_auth(self, testapp, db):
        resp = send(testapp, 'PUT', '/api/user', {'user': {'bio': 'x'}})
        assert resp.status_int == 401
        assert resp.json == {'msg': 'Missing Authorization Header'}

    # ORACLE: encodes current (buggy) behavior — revisit after upgrade
    @pytest.mark.oracle_known_bug
    @pytest.mark.parametrize('field,value,column', [
        ('email', 'bob@example.com', 'users.email'),
        ('username', 'bob', 'users.username'),
    ])
    def test_duplicate_raises_integrity_error(self, testapp, alice, bob, raises_unhandled,
                                              field, value, column):
        with pytest.raises(IntegrityError, match='UNIQUE constraint failed: ' + column):
            update(testapp, alice, **{field: value})

    # ORACLE: encodes current (buggy) behavior — revisit after upgrade
    @pytest.mark.oracle_known_bug
    @pytest.mark.parametrize('field,value', [('email', 'bob@example.com'), ('username', 'bob')])
    def test_duplicate_is_500(self, testapp, alice, bob, no_propagate, field, value):
        resp = update(testapp, alice, **{field: value})
        assert resp.status_int == 500
        assert SERVER_ERROR_HTML in resp.text


class TestRegisterConflicts:

    @pytest.mark.parametrize('username,email', [('alice', 'other@example.com'),
                                                ('other', 'alice@example.com')])
    def test_duplicate_username_or_email(self, testapp, alice, username, email):
        resp = send(testapp, 'POST', '/api/users', {'user': {
            'username': username, 'email': email, 'password': 'secret'}})
        assert resp.status_int == 422
        assert resp.json == USER_ALREADY_REGISTERED['message']

    def test_register_does_not_log_in_twice(self, testapp, alice):
        assert User.query.count() == 1
        assert UserProfile.query.count() == 1


class TestLoginEdges:

    def test_email_is_case_sensitive(self, testapp, alice):
        assert login_resp(testapp, 'ALICE@example.com', 'secret').status_int == 404

    def test_login_ignores_existing_authorization_header(self, testapp, alice, bob):
        resp = send(testapp, 'POST', '/api/users/login',
                    {'user': {'email': 'alice@example.com', 'password': 'secret'}}, token=bob)
        assert resp.status_int == 200
        assert resp.json['user']['username'] == 'alice'

    def test_each_login_issues_a_new_token(self, testapp, alice):
        first = login(testapp, 'alice@example.com', 'secret')
        second = login(testapp, 'alice@example.com', 'secret')
        assert first != second
        assert first != alice


def _encode(claims, secret=TestConfig.SECRET_KEY):
    return jwt.encode(claims, secret, algorithm='HS256')


class TestJwtEdges:

    @pytest.fixture
    def alice_user(self, alice):
        return User.query.filter_by(username='alice').one()

    def test_expired(self, testapp, alice_user):
        token = create_access_token(identity=alice_user, expires_delta=dt.timedelta(seconds=-10))
        resp = get_user(testapp, token)
        assert resp.status_int == 401
        assert resp.json == {'msg': 'Token has expired'}

    def test_refresh_token_rejected(self, testapp, alice_user):
        resp = get_user(testapp, create_refresh_token(identity=alice_user))
        assert resp.status_int == 422
        assert resp.json == {'msg': 'Only access tokens are allowed'}

    def test_token_for_deleted_user(self, testapp, alice, alice_user):
        alice_user.profile.delete()
        alice_user.delete()
        resp = get_user(testapp, alice)
        assert resp.status_int == 401
        assert resp.json == {'msg': 'Error loading the user 1'}

    def test_token_signed_with_prod_default_secret_is_rejected(self, testapp, alice_user):
        token = _encode({'identity': 1, 'type': 'access', 'fresh': False, 'jti': 'x'}, 'secret-key')
        resp = get_user(testapp, token)
        assert resp.status_int == 422
        assert resp.json == {'msg': 'Signature verification failed'}

    # ORACLE: encodes current (buggy) behavior — revisit after upgrade
    @pytest.mark.oracle_known_bug
    def test_token_without_exp_is_accepted(self, testapp, alice_user):
        token = _encode({'identity': 1, 'type': 'access', 'fresh': False, 'jti': 'x'})
        resp = get_user(testapp, token)
        assert resp.status_int == 200
        assert resp.json['user']['username'] == 'alice'

    def test_string_identity_is_accepted(self, testapp, alice_user):
        token = _encode({'identity': '1', 'type': 'access', 'fresh': False, 'jti': 'x'})
        assert get_user(testapp, token).json['user']['username'] == 'alice'

    def test_non_numeric_identity(self, testapp, alice_user):
        token = _encode({'identity': 'abc', 'type': 'access', 'fresh': False, 'jti': 'x'})
        resp = get_user(testapp, token)
        assert resp.status_int == 401
        assert resp.json == {'msg': 'Error loading the user abc'}

    @pytest.mark.parametrize('header', ['Token {0} Token {0}', 'Token {0} extra'])
    def test_extra_header_parts(self, testapp, alice, header):
        resp = send(testapp, 'GET', '/api/user', headers={'Authorization': header.format(alice)})
        assert resp.status_int == 422
        assert resp.json == {'msg': "Bad Authorization header. Expected value 'Token <JWT>'"}

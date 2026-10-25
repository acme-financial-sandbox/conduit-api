# coding: utf-8
"""Oracle characterization tests for ``conduit/user/views.py`` and JWT handling."""
import jwt
import pytest
from flask import url_for

from conduit.exceptions import USER_NOT_FOUND
from conduit.settings import TestConfig

from .oracle_helpers import auth, register

USER_KEYS = {'bio', 'createdAt', 'email', 'image', 'token', 'updatedAt', 'username'}
BAD_HEADER = {'msg': "Bad Authorization header. Expected 'Authorization: Token <JWT>'"}
MISSING_TYPE = {'msg': "Missing 'Token' type in 'Authorization' header. Expected 'Authorization: Token <JWT>'"}


@pytest.fixture
def token(testapp, db):
    return register(testapp, 'alice', password='correct-horse')


class TestLoginFailures:

    # ORACLE: encodes current (buggy) behavior — revisit after upgrade
    @pytest.mark.oracle_known_bug
    def test_wrong_password_is_404_user_not_found(self, testapp, token):
        resp = testapp.post_json(url_for('user.login_user'), {'user': {
            'email': 'alice@example.com', 'password': 'wrong'
        }}, expect_errors=True)
        assert resp.status_int == 404
        assert resp.json == USER_NOT_FOUND['message']
        assert resp.json == {'errors': {'body': ['User not found']}}

    def test_unknown_email_is_404_user_not_found(self, testapp, db):
        resp = testapp.post_json(url_for('user.login_user'), {'user': {
            'email': 'nobody@example.com', 'password': 'whatever'
        }}, expect_errors=True)
        assert resp.status_int == 404
        assert resp.json == USER_NOT_FOUND['message']

    def test_login_success_shape(self, testapp, token):
        resp = testapp.post_json(url_for('user.login_user'), {'user': {
            'email': 'alice@example.com', 'password': 'correct-horse'
        }})
        assert resp.status_int == 200
        assert list(resp.json) == ['user']
        assert set(resp.json['user']) == USER_KEYS


class TestJwtRequired:

    def test_missing_token(self, testapp, db):
        resp = testapp.get(url_for('user.get_user'), expect_errors=True)
        assert resp.status_int == 401
        assert resp.json == {'msg': 'Missing Authorization Header'}

    def test_malformed_token(self, testapp, db):
        resp = testapp.get(url_for('user.get_user'), headers=auth('not-a-jwt'), expect_errors=True)
        assert resp.status_int == 422
        assert resp.json == {'msg': 'Not enough segments'}

    def test_bad_signature(self, testapp, token):
        forged = jwt.encode(jwt.decode(token, options={'verify_signature': False}), 'wrong-secret',
                            algorithm='HS256')
        resp = testapp.get(url_for('user.get_user'), headers=auth(forged), expect_errors=True)
        assert resp.status_int == 422
        assert resp.json == {'msg': 'Signature verification failed'}

    @pytest.mark.parametrize('header', ['Bearer {}', 'token {}', '{}'])
    def test_wrong_scheme_counts_as_missing(self, testapp, token, header):
        resp = testapp.get(url_for('user.get_user'),
                           headers={'Authorization': header.format(token)}, expect_errors=True)
        assert resp.status_int == 401
        assert resp.json == MISSING_TYPE

    def test_scheme_without_token(self, testapp, token):
        resp = testapp.get(url_for('user.get_user'),
                           headers={'Authorization': 'Token'}, expect_errors=True)
        assert resp.status_int == 422
        assert resp.json == BAD_HEADER


class TestGetUser:

    # ORACLE: encodes current (buggy) behavior — revisit after upgrade
    @pytest.mark.oracle_known_bug
    def test_echoes_token_parsed_from_raw_header(self, testapp, token):
        """``get_user`` splits ``HTTP_AUTHORIZATION`` on 'Token ' instead of issuing a token."""
        resp = testapp.get(url_for('user.get_user'), headers=auth(token))
        assert resp.status_int == 200
        assert resp.json['user']['token'] == token
        assert resp.json['user']['username'] == 'alice'
        assert set(resp.json['user']) == USER_KEYS


class TestTokens:

    def _claims(self, token):
        return jwt.decode(token, TestConfig.SECRET_KEY, algorithms=['HS256'])

    def test_register_token_claims(self, testapp, token):
        claims = self._claims(token)
        assert set(claims) == {'exp', 'fresh', 'iat', 'identity', 'jti', 'nbf', 'type'}
        assert claims['identity'] == 1
        assert claims['fresh'] is False
        assert claims['type'] == 'access'
        assert claims['exp'] - claims['iat'] == 15 * 60

    def test_login_token_is_fresh(self, testapp, token):
        resp = testapp.post_json(url_for('user.login_user'), {'user': {
            'email': 'alice@example.com', 'password': 'correct-horse'
        }})
        claims = self._claims(resp.json['user']['token'])
        assert claims['fresh'] is True
        assert claims['identity'] == 1

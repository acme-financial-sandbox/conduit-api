# coding: utf-8
"""Oracle characterization tests for request-body validation (``use_kwargs`` + marshmallow).

Missing required fields and missing envelopes are not validated: they reach the view and blow up
(500). Schema validation errors are 422s rendered as Werkzeug HTML with no field details.
"""
import re

import pytest

from .oracle_helpers import make_article, send

SERVER_ERROR_HTML = '<title>500 Internal Server Error</title>'
UNPROCESSABLE_HTML = '<title>422 Unprocessable Entity</title>'
BAD_REQUEST_HTML = '<title>400 Bad Request</title>'
FORM = 'application/x-www-form-urlencoded'

# (id, method, url, json body or raw bytes, content type, needs auth, exception, message)
UNHANDLED = [
    ('register_missing_username', 'POST', '/api/users',
     {'user': {'email': 'q@example.com', 'password': 'p'}}, None, False,
     TypeError, "register_user() missing 1 required positional argument: 'username'"),
    ('register_missing_email', 'POST', '/api/users',
     {'user': {'username': 'q', 'password': 'p'}}, None, False,
     TypeError, "register_user() missing 1 required positional argument: 'email'"),
    ('register_missing_password', 'POST', '/api/users',
     {'user': {'username': 'q', 'email': 'q@example.com'}}, None, False,
     TypeError, "register_user() missing 1 required positional argument: 'password'"),
    ('register_no_envelope', 'POST', '/api/users',
     {'username': 'q', 'email': 'q@example.com', 'password': 'p'}, None, False, KeyError, "'user'"),
    ('register_empty_body', 'POST', '/api/users', b'', None, False, KeyError, "'user'"),
    ('register_form_body', 'POST', '/api/users', b'user=q', FORM, False, KeyError, "'user'"),
    ('login_missing_password', 'POST', '/api/users/login',
     {'user': {'email': 'alice@example.com'}}, None, False,
     TypeError, "login_user() missing 1 required positional argument: 'password'"),
    ('login_no_envelope', 'POST', '/api/users/login',
     {'email': 'alice@example.com', 'password': 'secret'}, None, False, KeyError, "'user'"),
    ('update_user_no_envelope', 'PUT', '/api/user', {'bio': 'x'}, None, True, KeyError, "'user'"),
    ('article_missing_title', 'POST', '/api/articles',
     {'article': {'description': 'd', 'body': 'b'}}, None, True,
     TypeError, "make_article() missing 1 required positional argument: 'title'"),
    ('article_missing_description', 'POST', '/api/articles',
     {'article': {'title': 'T', 'body': 'b'}}, None, True,
     TypeError, "make_article() missing 1 required positional argument: 'description'"),
    ('article_missing_body', 'POST', '/api/articles',
     {'article': {'title': 'T', 'description': 'd'}}, None, True,
     TypeError, "make_article() missing 1 required positional argument: 'body'"),
    ('article_no_envelope', 'POST', '/api/articles',
     {'title': 'T', 'description': 'd', 'body': 'b'}, None, True, KeyError, "'article'"),
    ('article_with_slug', 'POST', '/api/articles',
     {'article': {'title': 'T', 'description': 'd', 'body': 'b', 'slug': 'custom'}}, None, True,
     TypeError, "make_article() got an unexpected keyword argument 'slug'"),
    ('article_with_created_at', 'POST', '/api/articles',
     {'article': {'title': 'T', 'description': 'd', 'body': 'b',
                  'createdAt': '2000-01-01T00:00:00'}}, None, True,
     TypeError, "make_article() got an unexpected keyword argument 'createdAt'"),
    ('update_article_no_envelope', 'PUT', '/api/articles/orig', {'body': 'x'}, None, True,
     KeyError, "'article'"),
    ('comment_missing_body', 'POST', '/api/articles/orig/comments', {'comment': {}}, None, True,
     TypeError, "make_comment_on_article() missing 1 required positional argument: 'body'"),
    ('comment_no_envelope', 'POST', '/api/articles/orig/comments', {'body': 'x'}, None, True,
     KeyError, "'comment'"),
]

# (id, method, url, json body, needs auth)
UNPROCESSABLE = [
    ('register_invalid_email', 'POST', '/api/users',
     {'user': {'username': 'q', 'email': 'nope', 'password': 'p'}}, False),
    ('register_invalid_image_url', 'POST', '/api/users',
     {'user': {'username': 'q', 'email': 'q@example.com', 'password': 'p', 'image': 'nope'}}, False),
    ('register_unknown_field', 'POST', '/api/users',
     {'user': {'username': 'q', 'email': 'q@example.com', 'password': 'p', 'foo': 1}}, False),
    ('register_null_bio', 'POST', '/api/users',
     {'user': {'username': 'q', 'email': 'q@example.com', 'password': 'p', 'bio': None}}, False),
    ('update_user_token_field', 'PUT', '/api/user', {'user': {'token': 'abc'}}, True),
    ('update_user_created_at', 'PUT', '/api/user', {'user': {'createdAt': '2000-01-01T00:00:00'}}, True),
    ('update_article_null_title', 'PUT', '/api/articles/orig', {'article': {'title': None}}, True),
    ('update_article_unknown_field', 'PUT', '/api/articles/orig', {'article': {'foo': 1}}, True),
    ('comment_unknown_field', 'POST', '/api/articles/orig/comments',
     {'comment': {'body': 'x', 'foo': 1}}, True),
    ('list_articles_non_int_limit', 'GET', '/api/articles', {'limit': 'x'}, False),
    ('list_articles_unknown_key', 'GET', '/api/articles', {'page': 1}, False),
    ('feed_non_int_offset', 'GET', '/api/articles/feed', {'offset': 'x'}, True),
]


def _ids(cases):
    return [case[0] for case in cases]


@pytest.fixture
def orig(testapp, alice):
    """``alice`` with one article, slug ``orig``."""
    make_article(testapp, alice, title='Orig')
    return alice


def _raw_and_type(body, content_type):
    if isinstance(body, bytes):
        return body, content_type or 'application/json'
    return None, 'application/json'


class TestUnvalidatedInput:

    # ORACLE: encodes current (buggy) behavior — revisit after upgrade
    @pytest.mark.oracle_known_bug
    @pytest.mark.parametrize('name,method,url,body,content_type,needs_auth,exc,message', UNHANDLED,
                             ids=_ids(UNHANDLED))
    def test_raises(self, testapp, orig, raises_unhandled,
                    name, method, url, body, content_type, needs_auth, exc, message):
        raw, content_type = _raw_and_type(body, content_type)
        with pytest.raises(exc, match=re.escape(message)):
            send(testapp, method, url, data=None if raw is not None else body, raw=raw,
                 content_type=content_type, token=orig if needs_auth else None)

    # ORACLE: encodes current (buggy) behavior — revisit after upgrade
    @pytest.mark.oracle_known_bug
    @pytest.mark.parametrize('name,method,url,body,content_type,needs_auth,exc,message', UNHANDLED,
                             ids=_ids(UNHANDLED))
    def test_is_500(self, testapp, orig, no_propagate,
                    name, method, url, body, content_type, needs_auth, exc, message):
        raw, content_type = _raw_and_type(body, content_type)
        resp = send(testapp, method, url, data=None if raw is not None else body, raw=raw,
                    content_type=content_type, token=orig if needs_auth else None)
        assert resp.status_int == 500
        assert SERVER_ERROR_HTML in resp.text


class TestSchemaValidation:

    # ORACLE: encodes current (buggy) behavior — revisit after upgrade
    @pytest.mark.oracle_known_bug
    @pytest.mark.parametrize('name,method,url,body,needs_auth', UNPROCESSABLE, ids=_ids(UNPROCESSABLE))
    def test_422_is_html_without_field_errors(self, testapp, orig, name, method, url, body, needs_auth):
        resp = send(testapp, method, url, data=body, token=orig if needs_auth else None)
        assert resp.status_int == 422
        assert resp.headers['Content-Type'] == 'text/html; charset=utf-8'
        assert UNPROCESSABLE_HTML in resp.text

    def test_rejected_input_is_not_persisted(self, testapp, orig):
        send(testapp, 'POST', '/api/users', {'user': {'username': 'q', 'email': 'nope', 'password': 'p'}})
        resp = send(testapp, 'GET', '/api/profiles/q')
        assert resp.status_int == 404

    @pytest.mark.parametrize('url', ['/api/users', '/api/users/login'])
    def test_malformed_json_is_400_html(self, testapp, db, url):
        resp = send(testapp, 'POST', url, raw=b'{not json')
        assert resp.status_int == 400
        assert resp.headers['Content-Type'] == 'text/html; charset=utf-8'
        assert BAD_REQUEST_HTML in resp.text

    def test_valid_optional_fields_on_register(self, testapp, db):
        resp = send(testapp, 'POST', '/api/users', {'user': {
            'username': 'q', 'email': 'q@example.com', 'password': 'p', 'bio': 'hi',
            'image': 'http://img.example.com/a.png'}})
        assert resp.status_int == 200
        assert resp.json['user']['bio'] == 'hi'
        assert resp.json['user']['image'] == 'http://img.example.com/a.png'

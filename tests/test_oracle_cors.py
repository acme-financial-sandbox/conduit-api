# coding: utf-8
"""Oracle characterization tests for CORS (Flask-Cors on each blueprint) and generic HTTP handling."""
import pytest

from conduit.settings import Config

from .oracle_helpers import send

ALLOWED = 'http://localhost:4100'
ALL_METHODS = 'DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT'


def preflight(testapp, url, origin, method='GET', headers=None):
    request_headers = {'Origin': origin, 'Access-Control-Request-Method': method}
    if headers:
        request_headers['Access-Control-Request-Headers'] = headers
    return testapp.options(url, headers=request_headers, expect_errors=True)


class TestCors:

    def test_whitelist_is_inherited_by_test_config(self, app):
        assert app.config['CORS_ORIGIN_WHITELIST'] == Config.CORS_ORIGIN_WHITELIST

    @pytest.mark.parametrize('origin', Config.CORS_ORIGIN_WHITELIST)
    def test_whitelisted_origin_is_echoed(self, testapp, db, origin):
        resp = testapp.get('/api/tags', headers={'Origin': origin})
        assert resp.headers['Access-Control-Allow-Origin'] == origin
        assert resp.headers['Vary'] == 'Origin'

    def test_other_origin_gets_no_cors_headers(self, testapp, db):
        resp = testapp.get('/api/tags', headers={'Origin': 'http://evil.example.com'})
        assert resp.status_int == 200
        assert 'Access-Control-Allow-Origin' not in resp.headers

    def test_no_origin_gets_first_sorted_whitelist_entry(self, testapp, db):
        """Flask-Cors ``always_send``: with no ``Origin`` header it still sends an origin."""
        resp = testapp.get('/api/tags')
        assert resp.headers['Access-Control-Allow-Origin'] == sorted(Config.CORS_ORIGIN_WHITELIST)[0]
        assert resp.headers['Access-Control-Allow-Origin'] == 'http://0.0.0.0:4000'
        assert resp.headers['Vary'] == 'Origin'

    def test_preflight(self, testapp, db):
        resp = preflight(testapp, '/api/user', ALLOWED, method='PUT', headers='authorization,content-type')
        assert resp.status_int == 200
        assert resp.body == b''
        assert resp.headers['Access-Control-Allow-Origin'] == ALLOWED
        assert resp.headers['Access-Control-Allow-Methods'] == ALL_METHODS
        assert resp.headers['Access-Control-Allow-Headers'] == 'authorization, content-type'
        assert 'Access-Control-Allow-Credentials' not in resp.headers
        assert 'Access-Control-Max-Age' not in resp.headers

    def test_preflight_other_origin(self, testapp, db):
        resp = preflight(testapp, '/api/tags', 'http://evil.example.com')
        assert resp.status_int == 200
        assert 'Access-Control-Allow-Origin' not in resp.headers

    def test_error_responses_from_blueprints_carry_cors(self, testapp, db):
        resp = testapp.get('/api/user', headers={'Origin': ALLOWED}, expect_errors=True)
        assert resp.status_int == 401
        assert resp.headers['Access-Control-Allow-Origin'] == ALLOWED

    def test_unknown_route_has_no_cors(self, testapp, db):
        resp = testapp.get('/api/does-not-exist', headers={'Origin': ALLOWED}, expect_errors=True)
        assert resp.status_int == 404
        assert 'Access-Control-Allow-Origin' not in resp.headers


class TestHttpGenerics:

    def test_trailing_slash_is_accepted(self, testapp, db):
        resp = testapp.get('/api/tags/')
        assert resp.status_int == 200
        assert resp.json == {'tags': []}

    def test_head(self, testapp, db):
        resp = testapp.head('/api/tags')
        assert resp.status_int == 200
        assert resp.body == b''
        assert resp.headers['Content-Length'] == '17'

    def test_options_without_origin(self, testapp, db):
        resp = testapp.options('/api/tags')
        assert resp.status_int == 200
        assert resp.body == b''
        assert set(resp.headers['Allow'].split(', ')) == {'GET', 'HEAD', 'OPTIONS'}

    def test_root_is_404_html(self, testapp, db):
        resp = testapp.get('/', expect_errors=True)
        assert resp.status_int == 404
        assert resp.headers['Content-Type'] == 'text/html; charset=utf-8'

    def test_json_content_type(self, testapp, db):
        assert send(testapp, 'GET', '/api/tags').headers['Content-Type'] == 'application/json'

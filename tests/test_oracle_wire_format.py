# coding: utf-8
"""Oracle characterization of the JSON wire format (raw bytes and timestamp strings).

Other oracle tests compare parsed JSON and the golden files replace timestamps with
``<timestamp>``, so neither would notice a serializer or framework upgrade changing what
clients actually receive on the wire.
"""
import json
import re
from urllib.parse import quote

import pytest

from .oracle_helpers import make_article, make_comment, register, send

# Naive UTC from ``datetime.isoformat()``: no offset/``Z``; microseconds are dropped when zero.
TIMESTAMP = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{6})?$')


@pytest.fixture
def seeded(testapp, db):
    token = register(testapp, 'zoë', email='zoe@example.com')
    article = make_article(testapp, token, title='Café ünïcode', tags=['é'])
    make_comment(testapp, token, article['slug'], body='ç')
    return token, quote(article['slug'])


def _requests(seeded):
    token, slug = seeded
    return [
        ('POST', '/api/users/login', {'user': {'email': 'zoe@example.com', 'password': 'secret'}}, None),
        ('GET', '/api/user', None, token),
        ('GET', '/api/articles/' + slug, None, None),
        ('GET', '/api/articles', None, None),
        ('GET', '/api/articles/{}/comments'.format(slug), None, None),
        ('GET', '/api/profiles/' + quote('zoë'), None, None),
        ('GET', '/api/tags', None, None),
        ('GET', '/api/articles/missing', None, None),
        ('GET', '/api/user', None, None),
    ]


class TestJsonEncoding:
    """Flask 1.1 ``jsonify``: sorted keys, ASCII-only (``\\uXXXX``), trailing newline.

    Pretty-printed (indent 2, ``", "`` item separator) when ``app.debug`` is on, as under
    TestConfig/DevConfig; compact under ProdConfig (``DEBUG = False``)."""

    @pytest.mark.parametrize('debug, dumps_kwargs', [
        (True, {'indent': 2, 'separators': (', ', ': ')}),
        (False, {'separators': (',', ':')}),
    ], ids=['debug', 'prod'])
    def test_raw_body(self, app, testapp, seeded, debug, dumps_kwargs):
        app.debug = debug
        for method, url, data, token in _requests(seeded):
            resp = send(testapp, method, url, data, token=token)
            expected = json.dumps(resp.json, sort_keys=True, ensure_ascii=True, **dumps_kwargs) + '\n'
            assert resp.body == expected.encode('ascii'), (method, url)

    def test_non_ascii_is_escaped(self, app, testapp, seeded):
        app.debug = False
        body = send(testapp, 'GET', '/api/tags').body
        assert body == b'{"tags":["\\u00e9"]}\n'

    def test_debug_indent_has_trailing_spaces(self, testapp, seeded):
        body = send(testapp, 'GET', '/api/articles/missing').body
        assert body == b'{\n  "errors": {\n    "body": [\n      "Article not found"\n    ]\n  }\n}\n'


class TestTimestamps:

    def test_server_generated_format(self, testapp, seeded):
        token, slug = seeded
        user = send(testapp, 'GET', '/api/user', token=token).json['user']
        article = send(testapp, 'GET', '/api/articles/' + slug).json['article']
        comment = send(testapp, 'GET', '/api/articles/{}/comments'.format(slug)).json['comments'][0]
        for record in (user, article, comment):
            for key in ('createdAt', 'updatedAt'):
                assert TIMESTAMP.match(record[key]), (key, record[key])

    def test_offset_input_is_stored_naive_with_offset_dropped(self, testapp, seeded):
        token, slug = seeded
        resp = send(testapp, 'PUT', '/api/articles/' + slug,
                    {'article': {'createdAt': '2000-01-01T12:00:00+02:00'}}, token=token)
        assert resp.json['article']['createdAt'] == '2000-01-01T12:00:00'

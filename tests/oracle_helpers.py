# coding: utf-8
"""Shared helpers for the oracle characterization and golden-master tests."""
import json
import os

from flask import url_for

GOLDEN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'golden')
UPDATE_GOLDEN_ENV = 'ORACLE_UPDATE_GOLDEN'

VOLATILE_KEYS = {
    'token': '<token>',
    'createdAt': '<timestamp>',
    'updatedAt': '<timestamp>',
}


def auth(token):
    return {'Authorization': 'Token {}'.format(token)}


def register(testapp, username, email=None, password='secret'):
    """Register a user over HTTP and return the auth token."""
    resp = testapp.post_json(url_for('user.register_user'), {'user': {
        'username': username,
        'email': email or '{}@example.com'.format(username),
        'password': password,
    }})
    return resp.json['user']['token']


def login(testapp, email, password):
    resp = testapp.post_json(url_for('user.login_user'), {'user': {
        'email': email,
        'password': password,
    }})
    return resp.json['user']['token']


def make_article(testapp, token, title='How to train your dragon', tags=None, **extra):
    article = {
        'title': title,
        'description': 'Ever wonder how?',
        'body': 'You have to believe',
    }
    if tags is not None:
        article['tagList'] = tags
    article.update(extra)
    resp = testapp.post_json(url_for('articles.make_article'), {'article': article},
                             headers=auth(token))
    return resp.json['article']


def make_comment(testapp, token, slug, body='Nice article'):
    resp = testapp.post_json(url_for('articles.make_comment_on_article', slug=slug),
                             {'comment': {'body': body}}, headers=auth(token))
    return resp.json['comment']


def send(testapp, method, url, data=None, token=None, raw=None,
         content_type='application/json', headers=None):
    """Raw request with an optional JSON body (also on GET/DELETE); never raises on 4xx/5xx."""
    if raw is None:
        raw = b'' if data is None else json.dumps(data).encode('utf-8')
    all_headers = dict(auth(token)) if token else {}
    all_headers.update(headers or {})
    return testapp.request(url, method=method, body=raw, content_type=content_type,
                           headers=all_headers, expect_errors=True)


def normalize(data):
    """Replace volatile values (tokens, timestamps) with stable placeholders."""
    if isinstance(data, dict):
        return {key: (VOLATILE_KEYS[key] if key in VOLATILE_KEYS and value is not None
                      else normalize(value))
                for key, value in data.items()}
    if isinstance(data, list):
        return [normalize(item) for item in data]
    return data


def snapshot(resp):
    """Normalized, comparable representation of a webtest response."""
    content_type = resp.headers.get('Content-Type')
    if content_type == 'application/json':
        body = normalize(resp.json)
    else:
        body = resp.text
    return {'status': resp.status_int, 'content_type': content_type, 'body': body}


def _golden_path(name):
    return os.path.join(GOLDEN_DIR, name)


def assert_matches_golden_text(name, actual):
    path = _golden_path(name)
    if os.environ.get(UPDATE_GOLDEN_ENV):
        with open(path, 'w') as fh:
            fh.write(actual)
    with open(path) as fh:
        expected = fh.read()
    assert actual == expected, 'Golden file {} differs; see docs/ORACLE.md'.format(name)


def assert_matches_golden_json(name, actual):
    text = json.dumps(actual, indent=2, sort_keys=True) + '\n'
    assert_matches_golden_text(name, text)

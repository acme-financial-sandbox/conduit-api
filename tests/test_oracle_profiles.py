# coding: utf-8
"""Oracle characterization tests for ``conduit/profile/views.py``."""
import pytest

from conduit.exceptions import USER_NOT_FOUND

from .oracle_helpers import send

PROFILE_KEYS = {'bio', 'email', 'following', 'image', 'username'}


def follow(testapp, token, username, method='POST'):
    return send(testapp, method, '/api/profiles/{}/follow'.format(username), token=token)


class TestGetProfile:

    def test_anonymous(self, testapp, alice):
        resp = send(testapp, 'GET', '/api/profiles/alice')
        assert resp.status_int == 200
        assert list(resp.json) == ['profile']
        assert resp.json['profile'] == {'bio': None, 'email': 'alice@example.com', 'following': False,
                                        'image': None, 'username': 'alice'}

    # ORACLE: encodes current (buggy) behavior — revisit after upgrade
    @pytest.mark.oracle_known_bug
    def test_exposes_email(self, testapp, alice):
        """Public profiles include the user's email address."""
        assert send(testapp, 'GET', '/api/profiles/alice').json['profile']['email'] == 'alice@example.com'

    def test_own_profile_not_following(self, testapp, alice):
        resp = send(testapp, 'GET', '/api/profiles/alice', token=alice)
        assert resp.json['profile']['following'] is False

    def test_following_flag(self, testapp, alice, bob):
        follow(testapp, bob, 'alice')
        assert send(testapp, 'GET', '/api/profiles/alice', token=bob).json['profile']['following'] is True
        assert send(testapp, 'GET', '/api/profiles/bob', token=alice).json['profile']['following'] is False

    def test_username_is_case_sensitive(self, testapp, alice):
        resp = send(testapp, 'GET', '/api/profiles/ALICE')
        assert resp.status_int == 404
        assert resp.json == USER_NOT_FOUND['message']


class TestFollow:

    @pytest.mark.parametrize('method', ['POST', 'DELETE'])
    def test_requires_auth(self, testapp, alice, method):
        resp = send(testapp, method, '/api/profiles/alice/follow')
        assert resp.status_int == 401
        assert resp.json == {'msg': 'Missing Authorization Header'}

    @pytest.mark.parametrize('method', ['POST', 'DELETE'])
    def test_missing_user(self, testapp, alice, method):
        resp = follow(testapp, alice, 'nobody', method)
        assert resp.status_int == 404
        assert resp.json == USER_NOT_FOUND['message']

    def test_follow_shape(self, testapp, alice, bob):
        resp = follow(testapp, bob, 'alice')
        assert resp.status_int == 200
        assert list(resp.json) == ['profile']
        assert set(resp.json['profile']) == PROFILE_KEYS
        assert resp.json['profile']['username'] == 'alice'
        assert resp.json['profile']['following'] is True

    def test_follow_twice_is_idempotent(self, testapp, alice, bob):
        follow(testapp, bob, 'alice')
        resp = follow(testapp, bob, 'alice')
        assert resp.status_int == 200
        assert resp.json['profile']['following'] is True

    def test_follow_self_is_silent_noop(self, testapp, alice):
        resp = follow(testapp, alice, 'alice')
        assert resp.status_int == 200
        assert resp.json['profile']['following'] is False

    def test_unfollow(self, testapp, alice, bob):
        follow(testapp, bob, 'alice')
        resp = follow(testapp, bob, 'alice', 'DELETE')
        assert resp.status_int == 200
        assert resp.json['profile']['following'] is False

    def test_unfollow_not_followed_is_noop(self, testapp, alice, bob):
        resp = follow(testapp, bob, 'alice', 'DELETE')
        assert resp.status_int == 200
        assert resp.json['profile']['following'] is False

    def test_follow_is_one_directional(self, testapp, alice, bob):
        follow(testapp, bob, 'alice')
        assert send(testapp, 'GET', '/api/articles/feed', token=alice).json['articles'] == []

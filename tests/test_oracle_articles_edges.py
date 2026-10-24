# coding: utf-8
"""More oracle characterization tests for ``conduit/articles/views.py`` edge cases."""
from urllib.parse import quote

import pytest
from sqlalchemy.exc import IntegrityError

from conduit.articles.models import favoriter_assoc, tag_assoc
from conduit.database import db as _db
from conduit.exceptions import ARTICLE_NOT_FOUND

from .oracle_helpers import make_article, make_comment, send

SERVER_ERROR_HTML = '<title>500 Internal Server Error</title>'


def slugs(resp):
    return [a['slug'] for a in resp.json['articles']]


class TestCreateArticle:

    def test_unicode_title_slug(self, testapp, alice):
        article = make_article(testapp, alice, title='Ça va? Ünïcode & Ω title!')
        assert article['slug'] == 'ça-va-ünïcode-ω-title'
        assert send(testapp, 'GET', quote('/api/articles/ça-va-ünïcode-ω-title')).status_int == 200

    def test_duplicate_tags_in_request_are_collapsed(self, testapp, alice):
        assert make_article(testapp, alice, tags=['a', 'a', 'b'])['tagList'] == ['a', 'b']

    def test_tags_are_reused_across_articles(self, testapp, alice):
        make_article(testapp, alice, title='One', tags=['a', 'b'])
        second = make_article(testapp, alice, title='Two', tags=['b', 'c'])
        assert second['tagList'] == ['b', 'c']
        assert send(testapp, 'GET', '/api/tags').json == {'tags': ['a', 'b', 'c']}

    def test_empty_tag_list(self, testapp, alice):
        assert make_article(testapp, alice, tags=[])['tagList'] == []

    def test_initial_counts(self, testapp, alice):
        article = make_article(testapp, alice)
        assert (article['favorited'], article['favoritesCount']) == (False, 0)
        assert article['createdAt'] != article['updatedAt']

    def test_title_longer_than_column_is_accepted_on_sqlite(self, testapp, alice):
        """``String(100)`` is not enforced by SQLite; PostgreSQL would reject this."""
        assert make_article(testapp, alice, title='L' * 150)['title'] == 'L' * 150

    def test_requires_auth(self, testapp, db):
        resp = send(testapp, 'POST', '/api/articles', {'article': {'title': 'T', 'description': 'd', 'body': 'b'}})
        assert resp.status_int == 401

    # ORACLE: encodes current (buggy) behavior — revisit after upgrade
    @pytest.mark.oracle_known_bug
    def test_duplicate_title_raises_integrity_error(self, testapp, alice, raises_unhandled):
        make_article(testapp, alice, title='Same')
        with pytest.raises(IntegrityError, match='UNIQUE constraint failed: article.slug'):
            make_article(testapp, alice, title='Same')

    # ORACLE: encodes current (buggy) behavior — revisit after upgrade
    @pytest.mark.oracle_known_bug
    def test_duplicate_title_is_500(self, testapp, alice, bob, no_propagate):
        make_article(testapp, alice, title='Same')
        resp = send(testapp, 'POST', '/api/articles',
                    {'article': {'title': 'Same', 'description': 'd', 'body': 'b'}}, token=bob)
        assert resp.status_int == 500
        assert SERVER_ERROR_HTML in resp.text


class TestUpdateArticleEdges:

    @pytest.fixture
    def orig(self, testapp, alice):
        return make_article(testapp, alice, title='Orig', tags=['t1'])

    def put(self, testapp, token, url_slug, **fields):
        return send(testapp, 'PUT', '/api/articles/{}'.format(url_slug), {'article': fields}, token=token)

    def test_empty_update_only_bumps_updated_at(self, testapp, alice, orig):
        resp = self.put(testapp, alice, 'orig')
        assert resp.status_int == 200
        updated = resp.json['article']
        assert updated['updatedAt'] != orig['updatedAt']
        assert {k: v for k, v in updated.items() if k != 'updatedAt'} == {
            k: v for k, v in orig.items() if k != 'updatedAt'}

    def test_partial_update(self, testapp, alice, orig):
        updated = self.put(testapp, alice, 'orig', body='new body').json['article']
        assert updated['body'] == 'new body'
        assert (updated['title'], updated['description']) == ('Orig', orig['description'])

    # ORACLE: encodes current (buggy) behavior — revisit after upgrade
    @pytest.mark.oracle_known_bug
    def test_body_slug_overrides_url_slug(self, testapp, alice, orig):
        """``use_kwargs`` passes the body's ``slug`` over the route's ``<slug>``."""
        resp = self.put(testapp, alice, 'does-not-exist', slug='orig', body='via body slug')
        assert resp.status_int == 200
        assert resp.json['article']['body'] == 'via body slug'
        resp = self.put(testapp, alice, 'orig', slug='renamed')
        assert resp.status_int == 404
        assert resp.json == ARTICLE_NOT_FOUND['message']

    # ORACLE: encodes current (buggy) behavior — revisit after upgrade
    @pytest.mark.oracle_known_bug
    def test_created_at_is_client_writable(self, testapp, alice, orig):
        updated = self.put(testapp, alice, 'orig', createdAt='2000-01-01T00:00:00').json['article']
        assert updated['createdAt'] == '2000-01-01T00:00:00'

    # ORACLE: encodes current (buggy) behavior — revisit after upgrade
    @pytest.mark.oracle_known_bug
    def test_tag_list_update_raises(self, testapp, alice, orig, raises_unhandled):
        with pytest.raises(AttributeError, match="'str' object has no attribute '_sa_instance_state'"):
            self.put(testapp, alice, 'orig', tagList=['t2'])

    # ORACLE: encodes current (buggy) behavior — revisit after upgrade
    @pytest.mark.oracle_known_bug
    def test_tag_list_update_is_500(self, testapp, alice, orig, no_propagate):
        resp = self.put(testapp, alice, 'orig', tagList=['t2'])
        assert resp.status_int == 500


class TestDeleteArticleEdges:

    def test_deleting_favorited_and_tagged_article_cleans_associations(self, testapp, alice, bob):
        make_article(testapp, alice, title='Tagged', tags=['q'])
        send(testapp, 'POST', '/api/articles/tagged/favorite', token=bob)
        assert send(testapp, 'DELETE', '/api/articles/tagged', token=alice).status_int == 200
        assert _db.session.execute(favoriter_assoc.select()).fetchall() == []
        assert _db.session.execute(tag_assoc.select()).fetchall() == []
        assert send(testapp, 'GET', '/api/tags').json == {'tags': ['q']}

    # ORACLE: encodes current (buggy) behavior — revisit after upgrade
    @pytest.mark.oracle_known_bug
    def test_article_with_comments_raises(self, testapp, alice, raises_unhandled):
        make_article(testapp, alice, title='Orig')
        make_comment(testapp, alice, 'orig')
        with pytest.raises(IntegrityError, match='NOT NULL constraint failed: comment.article_id'):
            send(testapp, 'DELETE', '/api/articles/orig', token=alice)

    # ORACLE: encodes current (buggy) behavior — revisit after upgrade
    @pytest.mark.oracle_known_bug
    def test_article_with_comments_is_500_and_survives(self, testapp, alice, no_propagate):
        make_article(testapp, alice, title='Orig')
        make_comment(testapp, alice, 'orig')
        resp = send(testapp, 'DELETE', '/api/articles/orig', token=alice)
        assert resp.status_int == 500
        _db.session.rollback()
        assert send(testapp, 'GET', '/api/articles/orig').status_int == 200

    def test_requires_auth(self, testapp, alice):
        make_article(testapp, alice, title='Orig')
        resp = send(testapp, 'DELETE', '/api/articles/orig')
        assert resp.status_int == 401


class TestFavoriteEdges:

    def test_favorite_twice_is_idempotent(self, testapp, alice):
        make_article(testapp, alice, title='Orig')
        send(testapp, 'POST', '/api/articles/orig/favorite', token=alice)
        resp = send(testapp, 'POST', '/api/articles/orig/favorite', token=alice)
        assert resp.status_int == 200
        assert (resp.json['article']['favorited'], resp.json['article']['favoritesCount']) == (True, 1)

    @pytest.mark.parametrize('method', ['POST', 'DELETE'])
    def test_requires_auth(self, testapp, alice, method):
        make_article(testapp, alice, title='Orig')
        resp = send(testapp, method, '/api/articles/orig/favorite')
        assert resp.status_int == 401
        assert resp.json == {'msg': 'Missing Authorization Header'}


class TestPaging:

    @pytest.fixture
    def many(self, testapp, alice):
        for i in range(22):
            make_article(testapp, alice, title='A{:02d}'.format(i))

    def test_default_limit_is_20_oldest_first(self, testapp, many):
        resp = send(testapp, 'GET', '/api/articles')
        assert slugs(resp) == ['a{:02d}'.format(i) for i in range(20)]
        assert resp.json['articlesCount'] == 20

    def test_negative_limit_returns_everything(self, testapp, many):
        assert len(slugs(send(testapp, 'GET', '/api/articles', {'limit': -1}))) == 22

    def test_offset_past_end(self, testapp, many):
        assert send(testapp, 'GET', '/api/articles', {'offset': 100}).json == {'articles': [], 'articlesCount': 0}

    def test_slug_lookup_is_case_sensitive(self, testapp, many):
        assert send(testapp, 'GET', '/api/articles/A00').status_int == 404


class TestCommentEdges:

    @pytest.fixture
    def orig(self, testapp, alice):
        return make_article(testapp, alice, title='Orig')

    def comment(self, testapp, token, **fields):
        return send(testapp, 'POST', '/api/articles/orig/comments', {'comment': fields}, token=token)

    def test_shape(self, testapp, alice, orig):
        resp = self.comment(testapp, alice, body='hi')
        assert resp.status_int == 200
        assert list(resp.json) == ['comment']
        assert resp.json['comment']['id'] == 1
        assert resp.json['comment']['author']['username'] == 'alice'

    def test_missing_article(self, testapp, alice):
        resp = send(testapp, 'POST', '/api/articles/nope/comments', {'comment': {'body': 'x'}}, token=alice)
        assert resp.status_int == 404
        assert resp.json == ARTICLE_NOT_FOUND['message']

    @pytest.mark.parametrize('method,url', [('POST', '/api/articles/orig/comments'),
                                            ('DELETE', '/api/articles/orig/comments/1')])
    def test_requires_auth(self, testapp, orig, method, url):
        resp = send(testapp, method, url, {'comment': {'body': 'x'}} if method == 'POST' else None)
        assert resp.status_int == 401

    def test_get_comments_is_public_and_ordered_by_id(self, testapp, alice, bob, orig):
        self.comment(testapp, alice, body='first')
        self.comment(testapp, bob, body='second')
        resp = send(testapp, 'GET', '/api/articles/orig/comments')
        assert [(c['id'], c['body'], c['author']['username']) for c in resp.json['comments']] == [
            (1, 'first', 'alice'), (2, 'second', 'bob')]

    # ORACLE: encodes current (buggy) behavior — revisit after upgrade
    @pytest.mark.oracle_known_bug
    def test_id_and_created_at_are_client_writable(self, testapp, alice, orig):
        comment = self.comment(testapp, alice, body='x', id=99, createdAt='2000-01-01T00:00:00').json['comment']
        assert (comment['id'], comment['createdAt']) == (99, '2000-01-01T00:00:00')

    # ORACLE: encodes current (buggy) behavior — revisit after upgrade
    @pytest.mark.oracle_known_bug
    def test_delete_non_numeric_id_raises(self, testapp, alice, orig, raises_unhandled):
        with pytest.raises(AttributeError, match="'NoneType' object has no attribute 'delete'"):
            send(testapp, 'DELETE', '/api/articles/orig/comments/abc', token=alice)

    # ORACLE: encodes current (buggy) behavior — revisit after upgrade
    @pytest.mark.oracle_known_bug
    def test_delete_comment_via_other_article_slug_is_500(self, testapp, alice, orig, no_propagate):
        make_article(testapp, alice, title='Other')
        cid = self.comment(testapp, alice, body='x').json['comment']['id']
        resp = send(testapp, 'DELETE', '/api/articles/other/comments/{}'.format(cid), token=alice)
        assert resp.status_int == 500
        assert len(send(testapp, 'GET', '/api/articles/orig/comments').json['comments']) == 1

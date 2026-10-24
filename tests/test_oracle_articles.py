# coding: utf-8
"""Oracle characterization tests for ``conduit/articles/views.py``.

These lock in CURRENT behavior (see docs/ORACLE.md); do not "fix" them to match the spec.
"""
import json

import pytest
from flask import url_for
from sqlalchemy.exc import OperationalError

from conduit.exceptions import ARTICLE_NOT_FOUND

from .oracle_helpers import auth, make_article, make_comment

ARTICLE_KEYS = {'author', 'body', 'createdAt', 'description', 'favorited', 'favoritesCount',
                'slug', 'tagList', 'title', 'updatedAt'}
PROFILE_KEYS = {'bio', 'email', 'following', 'image', 'username'}
COMMENT_KEYS = {'author', 'body', 'createdAt', 'id', 'updatedAt'}
SERVER_ERROR_HTML = '<title>500 Internal Server Error</title>'


def get_with_json_body(testapp, endpoint, body, **kwargs):
    """``use_kwargs`` (flask-apispec 0.11 / webargs 8) only reads the JSON body, even on GET."""
    return testapp.request(url_for(endpoint), method='GET', body=json.dumps(body).encode('utf-8'),
                           content_type='application/json', **kwargs)


def slugs(resp):
    return [a['slug'] for a in resp.json['articles']]


class TestGetArticle:

    def test_found(self, testapp, alice):
        created = make_article(testapp, alice, tags=['dragons', 'training'])
        resp = testapp.get(url_for('articles.get_article', slug=created['slug']))
        assert resp.status_int == 200
        assert list(resp.json) == ['article']
        article = resp.json['article']
        assert set(article) == ARTICLE_KEYS
        assert set(article['author']) == PROFILE_KEYS
        assert article['slug'] == 'how-to-train-your-dragon'
        assert article['title'] == 'How to train your dragon'
        assert article['tagList'] == ['dragons', 'training']
        assert article['author']['username'] == 'alice'
        assert article['author']['following'] is False
        assert article['favorited'] is False
        assert article['favoritesCount'] == 0

    def test_found_authenticated(self, testapp, alice):
        created = make_article(testapp, alice)
        resp = testapp.get(url_for('articles.get_article', slug=created['slug']),
                           headers=auth(alice))
        assert resp.status_int == 200
        assert resp.json['article']['slug'] == created['slug']
        assert resp.json['article']['favorited'] is False

    # ORACLE: encodes current (buggy) behavior — revisit after upgrade
    @pytest.mark.oracle_known_bug
    def test_identity_leaks_to_later_anonymous_requests_in_test_app(self, testapp, alice, bob):
        """Flask-JWT-Extended 3 caches the user on the app context, which the ``app`` fixture
        keeps pushed for the whole test, so an anonymous request still sees the last user."""
        created = make_article(testapp, alice)
        testapp.post(url_for('articles.favorite_an_article', slug=created['slug']), headers=auth(bob))
        testapp.post(url_for('profiles.follow_user', username='alice'), headers=auth(bob))
        resp = testapp.get(url_for('articles.get_article', slug=created['slug']))
        assert resp.json['article']['favorited'] is True
        assert resp.json['article']['author']['following'] is True

    def test_not_found(self, testapp, db):
        resp = testapp.get(url_for('articles.get_article', slug='missing'), expect_errors=True)
        assert resp.status_int == 404
        assert resp.json == ARTICLE_NOT_FOUND['message']
        assert resp.json == {'errors': {'body': ['Article not found']}}


class TestUpdateArticle:

    def test_owner_updates(self, testapp, alice):
        created = make_article(testapp, alice)
        resp = testapp.put_json(url_for('articles.update_article', slug=created['slug']), {
            'article': {'body': 'New body', 'title': 'A brand new title'}
        }, headers=auth(alice))
        assert resp.status_int == 200
        article = resp.json['article']
        assert set(article) == ARTICLE_KEYS
        assert article['body'] == 'New body'
        assert article['title'] == 'A brand new title'
        # Quirk: the slug is NOT regenerated when the title changes.
        assert article['slug'] == created['slug']
        assert article['description'] == created['description']

    def test_non_owner_gets_not_found(self, testapp, alice, bob):
        created = make_article(testapp, alice)
        resp = testapp.put_json(url_for('articles.update_article', slug=created['slug']), {
            'article': {'body': 'Hijacked'}
        }, headers=auth(bob), expect_errors=True)
        assert resp.status_int == 404
        assert resp.json == ARTICLE_NOT_FOUND['message']

    def test_missing_slug(self, testapp, alice):
        resp = testapp.put_json(url_for('articles.update_article', slug='missing'), {
            'article': {'body': 'x'}
        }, headers=auth(alice), expect_errors=True)
        assert resp.status_int == 404
        assert resp.json == ARTICLE_NOT_FOUND['message']

    def test_requires_auth(self, testapp, alice):
        created = make_article(testapp, alice)
        resp = testapp.put_json(url_for('articles.update_article', slug=created['slug']), {
            'article': {'body': 'x'}
        }, expect_errors=True)
        assert resp.status_int == 401
        assert resp.json == {'msg': 'Missing Authorization Header'}


class TestDeleteArticle:

    def test_owner_deletes(self, testapp, alice):
        created = make_article(testapp, alice)
        resp = testapp.delete(url_for('articles.delete_article', slug=created['slug']),
                              headers=auth(alice))
        assert resp.status_int == 200
        assert resp.headers['Content-Type'] == 'text/html; charset=utf-8'
        assert resp.body == b''
        resp = testapp.get(url_for('articles.get_article', slug=created['slug']), expect_errors=True)
        assert resp.status_int == 404

    # ORACLE: encodes current (buggy) behavior — revisit after upgrade
    @pytest.mark.oracle_known_bug
    def test_missing_slug_raises_attribute_error(self, testapp, alice, raises_unhandled):
        with pytest.raises(AttributeError, match="'NoneType' object has no attribute 'delete'"):
            testapp.delete(url_for('articles.delete_article', slug='missing'), headers=auth(alice))

    # ORACLE: encodes current (buggy) behavior — revisit after upgrade
    @pytest.mark.oracle_known_bug
    def test_missing_slug_is_500(self, testapp, alice, no_propagate):
        resp = testapp.delete(url_for('articles.delete_article', slug='missing'),
                              headers=auth(alice), expect_errors=True)
        assert resp.status_int == 500
        assert SERVER_ERROR_HTML in resp.text

    # ORACLE: encodes current (buggy) behavior — revisit after upgrade
    @pytest.mark.oracle_known_bug
    def test_non_owner_is_500_and_article_survives(self, testapp, alice, bob, no_propagate):
        created = make_article(testapp, alice)
        resp = testapp.delete(url_for('articles.delete_article', slug=created['slug']),
                              headers=auth(bob), expect_errors=True)
        assert resp.status_int == 500
        assert SERVER_ERROR_HTML in resp.text
        assert testapp.get(url_for('articles.get_article', slug=created['slug'])).status_int == 200


class TestFavorite:

    def test_unfavorite(self, testapp, alice, bob):
        created = make_article(testapp, alice)
        slug = created['slug']
        resp = testapp.post(url_for('articles.favorite_an_article', slug=slug), headers=auth(bob))
        assert resp.json['article']['favorited'] is True
        assert resp.json['article']['favoritesCount'] == 1

        resp = testapp.delete(url_for('articles.unfavorite_an_article', slug=slug), headers=auth(bob))
        assert resp.status_int == 200
        assert list(resp.json) == ['article']
        assert set(resp.json['article']) == ARTICLE_KEYS
        assert resp.json['article']['favorited'] is False
        assert resp.json['article']['favoritesCount'] == 0

    def test_unfavorite_not_favorited_is_noop(self, testapp, alice, bob):
        created = make_article(testapp, alice)
        resp = testapp.delete(url_for('articles.unfavorite_an_article', slug=created['slug']),
                              headers=auth(bob))
        assert resp.status_int == 200
        assert resp.json['article']['favoritesCount'] == 0

    def test_unfavorite_missing_article(self, testapp, bob):
        resp = testapp.delete(url_for('articles.unfavorite_an_article', slug='missing'),
                              headers=auth(bob), expect_errors=True)
        assert resp.status_int == 404
        assert resp.json == ARTICLE_NOT_FOUND['message']

    def test_favorite_missing_article(self, testapp, bob):
        resp = testapp.post(url_for('articles.favorite_an_article', slug='missing'),
                            headers=auth(bob), expect_errors=True)
        assert resp.status_int == 404
        assert resp.json == ARTICLE_NOT_FOUND['message']

    # ORACLE: encodes current (buggy) behavior — revisit after upgrade
    @pytest.mark.oracle_known_bug
    def test_favorited_state_leaks_across_articles(self, testapp, alice, bob):
        """``is_favourite``/``favorited`` check whether the user favorited ANY article."""
        first = make_article(testapp, alice, title='First')
        second = make_article(testapp, alice, title='Second')
        testapp.post(url_for('articles.favorite_an_article', slug=first['slug']), headers=auth(bob))

        resp = testapp.get(url_for('articles.get_article', slug=second['slug']), headers=auth(bob))
        assert resp.json['article']['favorited'] is True
        assert resp.json['article']['favoritesCount'] == 0

        # Favoriting the second article is silently skipped.
        resp = testapp.post(url_for('articles.favorite_an_article', slug=second['slug']),
                            headers=auth(bob))
        assert resp.status_int == 200
        assert resp.json['article']['favoritesCount'] == 0


class TestListArticles:

    def test_list_all(self, testapp, alice):
        make_article(testapp, alice, title='First')
        make_article(testapp, alice, title='Second')
        resp = testapp.get(url_for('articles.get_articles'))
        assert resp.status_int == 200
        assert set(resp.json) == {'articles', 'articlesCount'}
        assert slugs(resp) == ['first', 'second']
        assert resp.json['articlesCount'] == 2
        assert set(resp.json['articles'][0]) == ARTICLE_KEYS

    # ORACLE: encodes current (buggy) behavior — revisit after upgrade
    @pytest.mark.oracle_known_bug
    def test_query_string_filters_are_ignored(self, testapp, alice, bob):
        make_article(testapp, alice, title='One', tags=['dragons'])
        make_article(testapp, alice, title='Two')
        make_article(testapp, bob, title='Three')
        for params in ({'tag': 'dragons'}, {'author': 'bob'}, {'favorited': 'bob'},
                       {'limit': 1}, {'offset': 2}):
            resp = testapp.get(url_for('articles.get_articles', **params))
            assert slugs(resp) == ['one', 'two', 'three'], params
            assert resp.json['articlesCount'] == 3

    def test_limit_offset(self, testapp, alice):
        for title in ('One', 'Two', 'Three'):
            make_article(testapp, alice, title=title)
        resp = get_with_json_body(testapp, 'articles.get_articles', {'limit': 1, 'offset': 1})
        assert slugs(resp) == ['two']
        # Quirk: articlesCount is the page size, not the total.
        assert resp.json['articlesCount'] == 1

    def test_by_tag(self, testapp, alice):
        make_article(testapp, alice, title='Tagged', tags=['dragons'])
        make_article(testapp, alice, title='Untagged')
        resp = get_with_json_body(testapp, 'articles.get_articles', {'tag': 'dragons'})
        assert slugs(resp) == ['tagged']

    def test_by_author(self, testapp, alice, bob):
        make_article(testapp, alice, title='By alice')
        make_article(testapp, bob, title='By bob')
        resp = get_with_json_body(testapp, 'articles.get_articles', {'author': 'bob'})
        assert slugs(resp) == ['by-bob']

    def test_by_favorited(self, testapp, alice, bob):
        first = make_article(testapp, alice, title='First')
        make_article(testapp, alice, title='Second')
        testapp.post(url_for('articles.favorite_an_article', slug=first['slug']), headers=auth(bob))
        resp = get_with_json_body(testapp, 'articles.get_articles', {'favorited': 'bob'})
        assert slugs(resp) == ['first']

    def test_by_favorited_unknown_user(self, testapp, alice, bob):
        first = make_article(testapp, alice, title='First')
        testapp.post(url_for('articles.favorite_an_article', slug=first['slug']), headers=auth(bob))
        resp = get_with_json_body(testapp, 'articles.get_articles', {'favorited': 'nobody'})
        assert resp.json == {'articles': [], 'articlesCount': 0}

    # ORACLE: encodes current (buggy) behavior — revisit after upgrade
    @pytest.mark.oracle_known_bug
    def test_by_favorited_ignores_who_favorited(self, testapp, alice, bob):
        """The ``favorited`` filter cross-joins ``users``: any existing username matches."""
        first = make_article(testapp, alice, title='First')
        make_article(testapp, alice, title='Second')
        testapp.post(url_for('articles.favorite_an_article', slug=first['slug']), headers=auth(bob))
        resp = get_with_json_body(testapp, 'articles.get_articles', {'favorited': 'alice'})
        assert slugs(resp) == ['first']

    # ORACLE: encodes current (buggy) behavior — revisit after upgrade
    @pytest.mark.oracle_known_bug
    def test_author_and_favorited_together_raise(self, testapp, alice, bob, raises_unhandled):
        """Both filters join ``userprofile`` twice without aliasing -> ambiguous column."""
        make_article(testapp, alice, title='First')
        with pytest.raises(OperationalError, match='ambiguous column name: userprofile.id'):
            get_with_json_body(testapp, 'articles.get_articles', {'author': 'alice', 'favorited': 'bob'})

    # ORACLE: encodes current (buggy) behavior — revisit after upgrade
    @pytest.mark.oracle_known_bug
    def test_author_and_favorited_together_is_500(self, testapp, alice, bob, no_propagate):
        make_article(testapp, alice, title='First')
        resp = get_with_json_body(testapp, 'articles.get_articles', {'author': 'alice', 'favorited': 'bob'},
                                  expect_errors=True)
        assert resp.status_int == 500
        assert SERVER_ERROR_HTML in resp.text


class TestFeed:

    def test_requires_auth(self, testapp, db):
        resp = testapp.get(url_for('articles.articles_feed'), expect_errors=True)
        assert resp.status_int == 401
        assert resp.json == {'msg': 'Missing Authorization Header'}

    def test_empty_when_following_nobody(self, testapp, alice, bob):
        make_article(testapp, alice)
        resp = testapp.get(url_for('articles.articles_feed'), headers=auth(bob))
        assert resp.status_int == 200
        assert resp.json == {'articles': [], 'articlesCount': 0}

    def test_followed_authors_newest_first(self, testapp, alice, bob):
        make_article(testapp, alice, title='Older')
        make_article(testapp, alice, title='Newer')
        make_article(testapp, bob, title='Own article')
        testapp.post(url_for('profiles.follow_user', username='alice'), headers=auth(bob))
        resp = testapp.get(url_for('articles.articles_feed'), headers=auth(bob))
        assert resp.status_int == 200
        assert [a['slug'] for a in resp.json['articles']] == ['newer', 'older']
        assert resp.json['articlesCount'] == 2
        assert resp.json['articles'][0]['author']['username'] == 'alice'
        assert resp.json['articles'][0]['author']['following'] is True

    def test_limit_from_json_body(self, testapp, alice, bob):
        make_article(testapp, alice, title='Older')
        make_article(testapp, alice, title='Newer')
        testapp.post(url_for('profiles.follow_user', username='alice'), headers=auth(bob))
        resp = get_with_json_body(testapp, 'articles.articles_feed', {'limit': 1}, headers=auth(bob))
        assert slugs(resp) == ['newer']
        # Query-string paging is ignored, like in get_articles.
        resp = testapp.get(url_for('articles.articles_feed', limit=1), headers=auth(bob))
        assert slugs(resp) == ['newer', 'older']


class TestTags:

    def test_empty(self, testapp, db):
        resp = testapp.get(url_for('articles.get_tags'))
        assert resp.status_int == 200
        assert resp.json == {'tags': []}

    def test_distinct_tags_in_creation_order(self, testapp, alice):
        make_article(testapp, alice, title='One', tags=['b', 'a'])
        make_article(testapp, alice, title='Two', tags=['a', 'c'])
        resp = testapp.get(url_for('articles.get_tags'))
        assert resp.json == {'tags': ['b', 'a', 'c']}


class TestComments:

    def test_get_comments(self, testapp, alice, bob):
        created = make_article(testapp, alice)
        make_comment(testapp, alice, created['slug'], body='First!')
        make_comment(testapp, bob, created['slug'], body='Second!')
        resp = testapp.get(url_for('articles.get_comments', slug=created['slug']))
        assert resp.status_int == 200
        assert list(resp.json) == ['comments']
        comments = resp.json['comments']
        assert [c['body'] for c in comments] == ['First!', 'Second!']
        assert [c['author']['username'] for c in comments] == ['alice', 'bob']
        assert set(comments[0]) == COMMENT_KEYS
        assert set(comments[0]['author']) == PROFILE_KEYS

    def test_get_comments_empty(self, testapp, alice):
        created = make_article(testapp, alice)
        resp = testapp.get(url_for('articles.get_comments', slug=created['slug']))
        assert resp.json == {'comments': []}

    def test_get_comments_missing_article(self, testapp, db):
        resp = testapp.get(url_for('articles.get_comments', slug='missing'), expect_errors=True)
        assert resp.status_int == 404
        assert resp.json == ARTICLE_NOT_FOUND['message']

    def test_delete_comment(self, testapp, alice):
        created = make_article(testapp, alice)
        comment = make_comment(testapp, alice, created['slug'])
        resp = testapp.delete(url_for('articles.delete_comment_on_article', slug=created['slug'],
                                      cid=comment['id']), headers=auth(alice))
        assert resp.status_int == 200
        assert resp.headers['Content-Type'] == 'text/html; charset=utf-8'
        assert resp.body == b''
        resp = testapp.get(url_for('articles.get_comments', slug=created['slug']))
        assert resp.json == {'comments': []}

    def test_delete_comment_missing_article(self, testapp, alice):
        resp = testapp.delete(url_for('articles.delete_comment_on_article', slug='missing', cid=1),
                              headers=auth(alice), expect_errors=True)
        assert resp.status_int == 404
        assert resp.json == ARTICLE_NOT_FOUND['message']

    # ORACLE: encodes current (buggy) behavior — revisit after upgrade
    @pytest.mark.oracle_known_bug
    def test_delete_missing_comment_raises_attribute_error(self, testapp, alice, raises_unhandled):
        created = make_article(testapp, alice)
        with pytest.raises(AttributeError, match="'NoneType' object has no attribute 'delete'"):
            testapp.delete(url_for('articles.delete_comment_on_article', slug=created['slug'],
                                   cid=999), headers=auth(alice))

    # ORACLE: encodes current (buggy) behavior — revisit after upgrade
    @pytest.mark.oracle_known_bug
    def test_delete_missing_comment_is_500(self, testapp, alice, no_propagate):
        created = make_article(testapp, alice)
        resp = testapp.delete(url_for('articles.delete_comment_on_article', slug=created['slug'],
                                      cid=999), headers=auth(alice), expect_errors=True)
        assert resp.status_int == 500
        assert SERVER_ERROR_HTML in resp.text

    # ORACLE: encodes current (buggy) behavior — revisit after upgrade
    @pytest.mark.oracle_known_bug
    def test_delete_other_users_comment_is_500(self, testapp, alice, bob, no_propagate):
        created = make_article(testapp, alice)
        comment = make_comment(testapp, alice, created['slug'])
        resp = testapp.delete(url_for('articles.delete_comment_on_article', slug=created['slug'],
                                      cid=comment['id']), headers=auth(bob), expect_errors=True)
        assert resp.status_int == 500
        resp = testapp.get(url_for('articles.get_comments', slug=created['slug']))
        assert len(resp.json['comments']) == 1

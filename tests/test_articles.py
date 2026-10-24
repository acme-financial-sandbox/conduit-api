# coding: utf-8

import json

from flask import url_for
from datetime import datetime


class TestArticleViews:

    def test_get_articles_by_author(self, testapp, user):
        """Query-string ``author=`` is currently ignored (see test_oracle_articles.py); this passes
        because every article belongs to ``user``. The author branch is exercised by
        ``test_get_articles_by_author_branch``."""
        user = user.get()
        resp = testapp.post_json(url_for('user.login_user'), {'user': {
            'email': user.email,
            'password': 'myprecious'
        }})

        token = str(resp.json['user']['token'])
        for _ in range(2):
            testapp.post_json(url_for('articles.make_article'), {
                "article": {
                    "title": "How to train your dragon {}".format(_),
                    "description": "Ever wonder how?",
                    "body": "You have to believe",
                    "tagList": ["reactjs", "angularjs", "dragons"]
                }
            }, headers={
                'Authorization': 'Token {}'.format(token)
            })

        resp = testapp.get(url_for('articles.get_articles', author=user.username))
        assert len(resp.json['articles']) == 2

    def test_favorite_an_article(self, testapp, user):
        user = user.get()
        resp = testapp.post_json(url_for('user.login_user'), {'user': {
            'email': user.email,
            'password': 'myprecious'
        }})

        token = str(resp.json['user']['token'])
        resp1 = testapp.post_json(url_for('articles.make_article'), {
            "article": {
                "title": "How to train your dragon",
                "description": "Ever wonder how?",
                "body": "You have to believe",
                "tagList": ["reactjs", "angularjs", "dragons"]
            }
        }, headers={
            'Authorization': 'Token {}'.format(token)
        })

        resp = testapp.post(url_for('articles.favorite_an_article',
                                    slug=resp1.json['article']['slug']),
                            headers={
                                'Authorization': 'Token {}'.format(token)
                            })
        assert resp.json['article']['favorited']

    def test_get_articles_by_favoriter(self, testapp, user):
        """Exercise the ``favorited`` filter branch of ``get_articles``."""
        user = user.get()
        resp = testapp.post_json(url_for('user.login_user'), {'user': {
            'email': user.email,
            'password': 'myprecious'
        }})

        token = str(resp.json['user']['token'])
        slugs = []
        for _ in range(2):
            resp = testapp.post_json(url_for('articles.make_article'), {
                "article": {
                    "title": "How to train your dragon {}".format(_),
                    "description": "Ever wonder how?",
                    "body": "You have to believe",
                    "tagList": ["reactjs", "angularjs", "dragons"]
                }
            }, headers={
                'Authorization': 'Token {}'.format(token)
            })
            slugs.append(resp.json['article']['slug'])

        testapp.post(url_for('articles.favorite_an_article', slug=slugs[0]), headers={
            'Authorization': 'Token {}'.format(token)
        })

        # use_kwargs only parses the JSON body (webargs 8), so the filter must be sent there.
        resp = testapp.request(url_for('articles.get_articles'), method='GET',
                               body=json.dumps({'favorited': user.username}).encode('utf-8'),
                               content_type='application/json')
        assert [a['slug'] for a in resp.json['articles']] == [slugs[0]]
        assert resp.json['articlesCount'] == 1

    def test_get_articles_by_author_branch(self, testapp, user):
        """Exercise the ``author`` filter branch of ``get_articles``."""
        user = user.get()
        other = testapp.post_json(url_for('user.register_user'), {'user': {
            'username': 'other', 'email': 'other@example.com', 'password': 'pw'
        }})
        for token, title in ((testapp.post_json(url_for('user.login_user'), {'user': {
                'email': user.email, 'password': 'myprecious'}}).json['user']['token'], 'Mine'),
                             (other.json['user']['token'], 'Theirs')):
            testapp.post_json(url_for('articles.make_article'), {
                "article": {"title": title, "description": "d", "body": "b"}
            }, headers={'Authorization': 'Token {}'.format(token)})

        resp = testapp.request(url_for('articles.get_articles'), method='GET',
                               body=json.dumps({'author': user.username}).encode('utf-8'),
                               content_type='application/json')
        assert [a['slug'] for a in resp.json['articles']] == ['mine']

    def test_make_article(self, testapp, user):
        user = user.get()
        resp = testapp.post_json(url_for('user.login_user'), {'user': {
            'email': user.email,
            'password': 'myprecious'
        }})

        token = str(resp.json['user']['token'])
        resp = testapp.post_json(url_for('articles.make_article'), {
            "article": {
                "title": "How to train your dragon",
                "description": "Ever wonder how?",
                "body": "You have to believe",
                "tagList": ["reactjs", "angularjs", "dragons"]
            }
        }, headers={
            'Authorization': 'Token {}'.format(token)
        })
        assert resp.json['article']['author']['email'] == user.email
        assert resp.json['article']['body'] == 'You have to believe'

    def test_make_comment_correct_schema(self, testapp, user):
        from conduit.profile.serializers import profile_schema
        user = user.get()
        resp = testapp.post_json(url_for('user.login_user'), {'user': {
            'email': user.email,
            'password': 'myprecious'
        }})

        token = str(resp.json['user']['token'])
        resp = testapp.post_json(url_for('articles.make_article'), {
            "article": {
                "title": "How to train your dragon",
                "description": "Ever wonder how?",
                "body": "You have to believe",
                "tagList": ["reactjs", "angularjs", "dragons"]
            }
        }, headers={
            'Authorization': 'Token {}'.format(token)
        })
        slug = resp.json['article']['slug']
        # make a comment
        resp = testapp.post_json(url_for('articles.make_comment_on_article', slug=slug), {
            "comment": {
                "createdAt": datetime.now().isoformat(),
                "body": "You have to believe",
            }
        }, headers={
            'Authorization': 'Token {}'.format(token)
        })

        # check
        authorp = resp.json['comment']['author']
        del authorp['following']
        # assert profile_schema.dump(user).data['profile'] == authorp
        assert profile_schema.dump(user)['profile'] == authorp

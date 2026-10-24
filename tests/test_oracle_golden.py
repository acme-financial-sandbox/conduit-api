# coding: utf-8
"""Golden-master snapshot tests.

Compare the route map and normalized JSON responses against files committed under
``tests/golden/``. To deliberately re-record them, run with ``ORACLE_UPDATE_GOLDEN=1`` and
review the diff (see docs/ORACLE.md).
"""
import pytest
from flask import current_app, url_for

from .oracle_helpers import (assert_matches_golden_json, assert_matches_golden_text, auth,
                             make_article, make_comment, register, snapshot)


def render_url_map():
    """Every route with its endpoint, methods and arguments, like ``flask urls`` (commands.py)."""
    rules = sorted(current_app.url_map.iter_rules(), key=lambda rule: (rule.rule, rule.endpoint))
    lines = ['{} {} methods={} arguments={}'.format(
        rule.rule, rule.endpoint, ','.join(sorted(rule.methods)), ','.join(sorted(rule.arguments)))
        for rule in rules]
    return '\n'.join(lines) + '\n'


def test_url_map(app):
    assert_matches_golden_text('url_map.txt', render_url_map())


def _seed(testapp):
    """Deterministic fixture data shared by the response snapshots."""
    alice = register(testapp, 'alice')
    bob = register(testapp, 'bob')
    article = make_article(testapp, alice, tags=['dragons', 'training'])
    make_comment(testapp, bob, article['slug'], body='Great read')
    return alice, bob, article['slug']


def _register(testapp):
    return testapp.post_json(url_for('user.register_user'), {'user': {
        'username': 'carol', 'email': 'carol@example.com', 'password': 'secret'}})


def _register_duplicate(testapp):
    _seed(testapp)
    return testapp.post_json(url_for('user.register_user'), {'user': {
        'username': 'alice', 'email': 'alice@example.com', 'password': 'secret'}}, expect_errors=True)


def _login(testapp):
    _seed(testapp)
    return testapp.post_json(url_for('user.login_user'), {'user': {
        'email': 'alice@example.com', 'password': 'secret'}})


def _login_wrong_password(testapp):
    _seed(testapp)
    return testapp.post_json(url_for('user.login_user'), {'user': {
        'email': 'alice@example.com', 'password': 'wrong'}}, expect_errors=True)


def _get_user(testapp):
    alice, _, _ = _seed(testapp)
    return testapp.get(url_for('user.get_user'), headers=auth(alice))


def _get_user_missing_token(testapp):
    return testapp.get(url_for('user.get_user'), expect_errors=True)


def _get_user_bad_prefix(testapp):
    alice, _, _ = _seed(testapp)
    return testapp.get(url_for('user.get_user'), headers={'Authorization': 'Bearer ' + alice},
                       expect_errors=True)


def _make_article(testapp):
    alice = register(testapp, 'alice')
    return testapp.post_json(url_for('articles.make_article'), {'article': {
        'title': 'Golden article', 'description': 'desc', 'body': 'body',
        'tagList': ['golden']}}, headers=auth(alice))


def _get_article(testapp):
    _, bob, slug = _seed(testapp)
    return testapp.get(url_for('articles.get_article', slug=slug), headers=auth(bob))


def _get_article_not_found(testapp):
    return testapp.get(url_for('articles.get_article', slug='missing'), expect_errors=True)


def _list_articles(testapp):
    alice, _, _ = _seed(testapp)
    make_article(testapp, alice, title='Second article')
    return testapp.get(url_for('articles.get_articles'))


def _feed(testapp):
    _, bob, _ = _seed(testapp)
    testapp.post(url_for('profiles.follow_user', username='alice'), headers=auth(bob))
    return testapp.get(url_for('articles.articles_feed'), headers=auth(bob))


def _get_profile(testapp):
    _, bob, _ = _seed(testapp)
    return testapp.get(url_for('profiles.get_profile', username='alice'), headers=auth(bob))


def _get_profile_not_found(testapp):
    return testapp.get(url_for('profiles.get_profile', username='nobody'), expect_errors=True)


def _tags(testapp):
    _seed(testapp)
    return testapp.get(url_for('articles.get_tags'))


def _comments(testapp):
    _, _, slug = _seed(testapp)
    return testapp.get(url_for('articles.get_comments', slug=slug))


def _unknown_route(testapp):
    return testapp.get('/api/does-not-exist', expect_errors=True)


def _method_not_allowed(testapp):
    return testapp.post('/api/tags', expect_errors=True)


def _update_article(testapp):
    alice, _, slug = _seed(testapp)
    return testapp.put_json(url_for('articles.update_article', slug=slug),
                            {'article': {'body': 'Updated body'}}, headers=auth(alice))


def _delete_article(testapp):
    alice = register(testapp, 'alice')
    slug = make_article(testapp, alice)['slug']
    return testapp.delete(url_for('articles.delete_article', slug=slug), headers=auth(alice))


def _favorite(testapp):
    _, bob, slug = _seed(testapp)
    return testapp.post(url_for('articles.favorite_an_article', slug=slug), headers=auth(bob))


def _unfavorite(testapp):
    _, bob, slug = _seed(testapp)
    testapp.post(url_for('articles.favorite_an_article', slug=slug), headers=auth(bob))
    return testapp.delete(url_for('articles.unfavorite_an_article', slug=slug), headers=auth(bob))


def _make_comment(testapp):
    alice, _, slug = _seed(testapp)
    return testapp.post_json(url_for('articles.make_comment_on_article', slug=slug),
                             {'comment': {'body': 'Thanks'}}, headers=auth(alice))


def _delete_comment(testapp):
    _, bob, slug = _seed(testapp)
    return testapp.delete(url_for('articles.delete_comment_on_article', slug=slug, cid=1),
                          headers=auth(bob))


def _follow(testapp):
    _, bob, _ = _seed(testapp)
    return testapp.post(url_for('profiles.follow_user', username='alice'), headers=auth(bob))


def _unfollow(testapp):
    _, bob, _ = _seed(testapp)
    testapp.post(url_for('profiles.follow_user', username='alice'), headers=auth(bob))
    return testapp.delete(url_for('profiles.unfollow_user', username='alice'), headers=auth(bob))


def _update_user(testapp):
    alice, _, _ = _seed(testapp)
    return testapp.put_json(url_for('user.update_user'), {'user': {
        'bio': 'New bio', 'image': 'http://img.example.com/alice.png'}}, headers=auth(alice))


def _register_invalid_email(testapp):
    return testapp.post_json(url_for('user.register_user'), {'user': {
        'username': 'carol', 'email': 'not-an-email', 'password': 'secret'}}, expect_errors=True)


def _malformed_json(testapp):
    return testapp.post(url_for('user.register_user'), '{not json', content_type='application/json',
                        expect_errors=True)


def _comments_missing_article(testapp):
    return testapp.get(url_for('articles.get_comments', slug='missing'), expect_errors=True)


def _follow_missing_user(testapp):
    alice, _, _ = _seed(testapp)
    return testapp.post(url_for('profiles.follow_user', username='nobody'), headers=auth(alice),
                        expect_errors=True)


SCENARIOS = {
    'update_article': _update_article,
    'delete_article': _delete_article,
    'favorite': _favorite,
    'unfavorite': _unfavorite,
    'make_comment': _make_comment,
    'delete_comment': _delete_comment,
    'follow': _follow,
    'unfollow': _unfollow,
    'update_user': _update_user,
    'register_invalid_email': _register_invalid_email,
    'malformed_json': _malformed_json,
    'comments_missing_article': _comments_missing_article,
    'follow_missing_user': _follow_missing_user,
    'register': _register,
    'register_duplicate': _register_duplicate,
    'login': _login,
    'login_wrong_password': _login_wrong_password,
    'get_user': _get_user,
    'get_user_missing_token': _get_user_missing_token,
    'get_user_bad_prefix': _get_user_bad_prefix,
    'make_article': _make_article,
    'get_article': _get_article,
    'get_article_not_found': _get_article_not_found,
    'list_articles': _list_articles,
    'feed': _feed,
    'get_profile': _get_profile,
    'get_profile_not_found': _get_profile_not_found,
    'tags': _tags,
    'comments': _comments,
    'unknown_route': _unknown_route,
    'method_not_allowed': _method_not_allowed,
}


@pytest.mark.parametrize('name', sorted(SCENARIOS))
def test_response_snapshot(testapp, db, name):
    resp = SCENARIOS[name](testapp)
    record = {'request': '{} {}'.format(resp.request.method, resp.request.path_qs)}
    record.update(snapshot(resp))
    assert_matches_golden_json('responses/{}.json'.format(name), record)

# coding: utf-8
"""Oracle characterization tests for model/helper edge cases and the DB schema golden master."""
import pytest

from conduit.articles.models import Article, Comment, Tags
from conduit.database import db as _db
from conduit.exceptions import (ARTICLE_NOT_FOUND, COMMENT_NOT_OWNED, UNKNOWN_ERROR, USER_ALREADY_REGISTERED,
                                USER_NOT_FOUND, InvalidUsage)
from conduit.profile.models import UserProfile
from conduit.profile.serializers import profile_schema
from conduit.user.models import User

from .factories import UserFactory
from .oracle_helpers import assert_matches_golden_text


def render_schema(metadata):
    """Tables, columns, types, constraints and foreign keys, in a stable order."""
    lines = []
    for table in sorted(metadata.tables.values(), key=lambda t: t.name):
        lines.append(table.name)
        for col in table.columns:
            flags = [flag for flag, on in (('pk', col.primary_key), ('nullable', col.nullable),
                                           ('unique', col.unique)) if on]
            fks = ','.join(sorted(fk.target_fullname for fk in col.foreign_keys))
            lines.append('  {} {} {}{}'.format(col.name, repr(col.type), ','.join(flags) or '-',
                                               ' -> ' + fks if fks else ''))
    return '\n'.join(lines) + '\n'


def test_schema_golden(app):
    assert_matches_golden_text('schema.txt', render_schema(_db.metadata))


@pytest.fixture
def profile(db):
    user = UserFactory(password='x')
    db.session.commit()
    return UserProfile(user).save()


@pytest.fixture
def article(profile):
    return Article(profile, 'Title', 'body', 'desc').save()


@pytest.mark.usefixtures('db')
class TestModelEdges:

    def test_reprs(self, profile):
        assert repr(profile.user) == "<User('{}')>".format(profile.user.username)
        assert repr(Tags('python')) == 'python'

    def test_user_token_class_default(self, profile):
        assert User.token == ''
        assert profile.user.token == ''

    def test_profile_proxies_user_fields(self, profile):
        profile.user.update(bio='b', image='i')
        assert (profile.username, profile.email, profile.bio, profile.image) == (
            profile.user.username, profile.user.email, 'b', 'i')

    @pytest.mark.parametrize('record_id,found', [(1, True), ('1', True), (1.0, True), ('abc', False),
                                                 (None, False), ('', False), (2, False)])
    def test_get_by_id(self, profile, record_id, found):
        assert (User.get_by_id(record_id) is not None) is found

    def test_add_tag_twice(self, article):
        tag = Tags('x').save()
        assert article.add_tag(tag) is True
        assert article.add_tag(tag) is False
        assert article.tagList == [tag]

    def test_remove_missing_tag(self, article):
        assert article.remove_tag(Tags('x').save()) is False

    def test_flags_without_current_user(self, article, profile):
        assert article.favorited is False
        assert profile.following is False

    def test_favourite_twice(self, article, profile):
        assert article.favourite(profile) is True
        assert article.favourite(profile) is False
        assert article.favoritesCount == 1

    def test_unfavourite_not_favourited(self, article, profile):
        assert article.unfavourite(profile) is False

    def test_slug_defaults_to_slugified_title(self, profile):
        assert Article(profile, 'Ça va? Ünïcode & Ω title!', 'b', 'd').slug == 'ça-va-ünïcode-ω-title'
        assert Article(profile, 'T', 'b', 'd', slug='given').slug == 'given'

    def test_comment(self, article, profile):
        comment = Comment(article, profile, 'hi').save()
        assert comment.article is article
        assert article.comments.all() == [comment]
        assert profile.comments == [comment]

    def test_crud_mixin_without_commit(self, profile):
        user = profile.user
        assert user.update(commit=False, bio='pending') is user
        _db.session.rollback()
        assert User.get_by_id(user.id).bio is None

    def test_save_without_commit(self, db):
        tag = Tags('z').save(commit=False)
        assert tag in db.session
        db.session.rollback()
        assert Tags.query.count() == 0

    def test_delete_return_values(self, db):
        tag = Tags('x').save()
        assert tag.delete(commit=False) is False
        db.session.commit()
        assert Tags('y').save().delete() is None
        assert Tags.query.count() == 0


class TestExceptions:

    @pytest.mark.parametrize('factory,template,status', [
        (InvalidUsage.user_not_found, USER_NOT_FOUND, 404),
        (InvalidUsage.user_already_registered, USER_ALREADY_REGISTERED, 422),
        (InvalidUsage.unknown_error, UNKNOWN_ERROR, 500),
        (InvalidUsage.article_not_found, ARTICLE_NOT_FOUND, 404),
        (InvalidUsage.comment_not_owned, COMMENT_NOT_OWNED, 422),
    ])
    def test_factories(self, app, factory, template, status):
        error = factory()
        assert error.status_code == status == template['status_code']
        assert error.message == template['message']
        assert error.to_json().get_json() == template['message']

    def test_templates(self):
        assert UNKNOWN_ERROR['message'] == {'errors': {'body': []}}
        assert COMMENT_NOT_OWNED['message'] == {'errors': {'body': ['Not your article']}}

    def test_defaults(self):
        error = InvalidUsage('boom')
        assert (error.message, error.status_code, error.payload) == ('boom', 500, None)


def test_profile_schema_load_unwraps_envelope():
    assert profile_schema.load({'profile': {'username': 'u', 'bio': 'b'}}) == {'username': 'u', 'bio': 'b'}

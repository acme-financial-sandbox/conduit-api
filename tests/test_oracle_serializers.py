# coding: utf-8
"""Oracle characterization tests for serializer edge cases."""
import pytest
from marshmallow import ValidationError

from conduit.user.serializers import user_schema


class TestUserSchemaPreLoad:

    @pytest.mark.parametrize('value', ['', None])
    def test_empty_email_and_image_are_dropped(self, value):
        data = {'user': {'username': 'u', 'password': 'p', 'email': value, 'image': value}}
        assert user_schema.load(data) == {'username': 'u', 'password': 'p'}

    @pytest.mark.parametrize('value', ['', None])
    def test_empty_email_alone_is_dropped(self, value):
        data = {'user': {'email': value, 'image': 'https://example.com/me.png'}}
        assert user_schema.load(data) == {'image': 'https://example.com/me.png'}

    @pytest.mark.parametrize('value', ['', None])
    def test_empty_image_alone_is_dropped(self, value):
        data = {'user': {'email': 'u@example.com', 'image': value}}
        assert user_schema.load(data) == {'email': 'u@example.com'}

    def test_missing_keys(self):
        assert user_schema.load({'user': {}}) == {}

    def test_other_empty_fields_are_kept(self):
        assert user_schema.load({'user': {'bio': '', 'username': ''}}) == {'bio': '', 'username': ''}

    def test_null_bio_is_rejected(self):
        with pytest.raises(ValidationError) as exc:
            user_schema.load({'user': {'bio': None}})
        assert exc.value.messages == {'bio': ['Field may not be null.']}

    def test_invalid_email_is_rejected(self):
        with pytest.raises(ValidationError) as exc:
            user_schema.load({'user': {'email': 'not-an-email'}})
        assert exc.value.messages == {'email': ['Not a valid email address.']}

    def test_missing_envelope_raises_key_error(self):
        with pytest.raises(KeyError):
            user_schema.load({'email': 'u@example.com'})

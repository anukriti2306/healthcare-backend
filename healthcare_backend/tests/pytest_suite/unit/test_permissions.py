"""Unit tests for apps.core.permissions.IsCreatorOrReadOnly."""
from types import SimpleNamespace

import pytest
from rest_framework.test import APIRequestFactory

from apps.core.permissions import IsCreatorOrReadOnly

factory = APIRequestFactory()
permission = IsCreatorOrReadOnly()

OWNER_ID, STRANGER_ID = 1, 2


def request_as(method, user_id):
    request = getattr(factory, method.lower())("/")
    request.user = SimpleNamespace(id=user_id)
    return request


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
@pytest.mark.parametrize("user_id", [OWNER_ID, STRANGER_ID])
def test_safe_methods_are_open_to_every_user(method, user_id):
    obj = SimpleNamespace(created_by_id=OWNER_ID)
    assert permission.has_object_permission(request_as(method, user_id), None, obj)


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
def test_creator_may_modify(method):
    obj = SimpleNamespace(created_by_id=OWNER_ID)
    assert permission.has_object_permission(request_as(method, OWNER_ID), None, obj)


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
def test_other_users_may_not_modify(method):
    obj = SimpleNamespace(created_by_id=OWNER_ID)
    assert not permission.has_object_permission(request_as(method, STRANGER_ID), None, obj)


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
def test_orphaned_records_cannot_be_modified_by_anyone(method):
    """created_by is SET_NULL when the creator's account is deleted."""
    obj = SimpleNamespace(created_by_id=None)
    assert not permission.has_object_permission(request_as(method, STRANGER_ID), None, obj)


def test_denial_message_is_human_readable():
    assert "created" in permission.message

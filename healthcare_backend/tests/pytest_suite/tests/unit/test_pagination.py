"""Unit tests for the opt-in pagination class."""
import pytest
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.core.pagination import OptionalLimitOffsetPagination

factory = APIRequestFactory()


def get_limit(query_string=""):
    request = Request(factory.get(f"/items/{query_string}"))
    return OptionalLimitOffsetPagination().get_limit(request)


def test_is_disabled_unless_requested():
    assert OptionalLimitOffsetPagination.default_limit is None
    assert get_limit() is None


def test_honours_a_requested_limit():
    assert get_limit("?limit=25") == 25


def test_caps_limit_at_100():
    assert get_limit("?limit=5000") == 100


@pytest.mark.parametrize("bad", ["abc", "-5", "0", "1.5"])
def test_invalid_limit_falls_back_to_no_pagination(bad):
    assert get_limit(f"?limit={bad}") is None

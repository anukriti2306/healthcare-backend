"""Unit tests for the centralised error handler (apps.core.exceptions)."""
import logging
from unittest.mock import MagicMock

import pytest
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError
from django.http import Http404
from rest_framework import exceptions

from apps.core.exceptions import build_error, custom_exception_handler


@pytest.fixture
def context():
    return {"view": "FakeView"}


@pytest.fixture
def rollback_spy(monkeypatch):
    """Replace the transaction-rollback hook so unit tests can assert it fires."""
    spy = MagicMock()
    monkeypatch.setattr("apps.core.exceptions.set_rollback", spy)
    return spy


class TestBuildError:
    def test_without_details_omits_the_key(self):
        assert build_error(404, "not_found", "Nope.") == {
            "error": {"status": 404, "code": "not_found", "message": "Nope."}
        }

    def test_with_details_includes_them(self):
        body = build_error(400, "validation_error", "Bad.", {"age": ["Too low."]})
        assert body["error"]["details"] == {"age": ["Too low."]}

    def test_falsy_but_not_none_details_are_kept(self):
        # An empty dict is still "details were provided".
        assert "details" in build_error(400, "validation_error", "Bad.", {})["error"]


class TestKnownExceptions:
    @pytest.mark.parametrize(
        ("exc", "status", "code"),
        [
            pytest.param(exceptions.NotAuthenticated(), 401, "not_authenticated", id="not-authenticated"),
            pytest.param(exceptions.AuthenticationFailed(), 401, "authentication_failed", id="auth-failed"),
            pytest.param(exceptions.PermissionDenied(), 403, "permission_denied", id="drf-permission-denied"),
            pytest.param(PermissionDenied(), 403, "permission_denied", id="django-permission-denied"),
            pytest.param(exceptions.NotFound(), 404, "not_found", id="drf-not-found"),
            pytest.param(Http404(), 404, "not_found", id="django-404"),
            pytest.param(exceptions.MethodNotAllowed("PUT"), 405, "method_not_allowed", id="method-not-allowed"),
            pytest.param(exceptions.ParseError(), 400, "parse_error", id="parse-error"),
            pytest.param(exceptions.UnsupportedMediaType("text/plain"), 415, "unsupported_media_type", id="415"),
            pytest.param(exceptions.Throttled(), 429, "throttled", id="throttled"),
        ],
    )
    def test_is_wrapped_in_the_standard_envelope(self, exc, status, code, context):
        response = custom_exception_handler(exc, context)
        assert response.status_code == status
        assert response.data["error"]["status"] == status
        assert response.data["error"]["code"] == code
        assert response.data["error"]["message"]
        assert "details" not in response.data["error"]

    def test_validation_errors_carry_field_details(self, context):
        exc = exceptions.ValidationError({"email": ["Enter a valid email address."]})
        response = custom_exception_handler(exc, context)
        assert response.status_code == 400
        assert response.data["error"]["code"] == "validation_error"
        assert response.data["error"]["details"] == {"email": ["Enter a valid email address."]}

    def test_list_style_validation_errors_are_supported(self, context):
        response = custom_exception_handler(exceptions.ValidationError(["Bad input."]), context)
        assert response.data["error"]["details"] == ["Bad input."]

    def test_response_headers_are_preserved(self, context):
        """Retry-After from DRF must survive the re-shaping of the body."""
        response = custom_exception_handler(exceptions.Throttled(wait=42), context)
        assert response["Retry-After"] == "42"


class TestIntegrityErrors:
    def test_is_translated_to_409_conflict(self, context, rollback_spy):
        response = custom_exception_handler(IntegrityError("duplicate key"), context)
        assert response.status_code == 409
        assert response.data["error"]["code"] == "conflict"

    def test_rolls_back_the_request_transaction(self, context, rollback_spy):
        custom_exception_handler(IntegrityError("duplicate key"), context)
        rollback_spy.assert_called_once()

    def test_database_message_is_not_leaked_to_the_client(self, context, rollback_spy):
        response = custom_exception_handler(
            IntegrityError('duplicate key value violates unique constraint "secret_idx"'), context
        )
        assert "secret_idx" not in str(response.data)

    def test_is_logged_for_operators(self, context, rollback_spy, caplog):
        with caplog.at_level(logging.WARNING, logger="apps.core.exceptions"):
            custom_exception_handler(IntegrityError("duplicate key"), context)
        assert any("IntegrityError" in record.getMessage() for record in caplog.records)


class TestUnhandledExceptions:
    def test_returns_generic_500_when_debug_is_off(self, settings, context, rollback_spy):
        settings.DEBUG = False
        response = custom_exception_handler(RuntimeError("db password is hunter2"), context)
        assert response.status_code == 500
        assert response.data["error"]["code"] == "server_error"
        assert "hunter2" not in str(response.data)
        rollback_spy.assert_called_once()

    def test_is_logged_with_traceback(self, settings, context, rollback_spy, caplog):
        settings.DEBUG = False
        with caplog.at_level(logging.ERROR, logger="apps.core.exceptions"):
            custom_exception_handler(RuntimeError("boom"), context)
        record = next(r for r in caplog.records if r.levelno == logging.ERROR)
        assert record.exc_info is not None

    def test_defers_to_django_debug_page_when_debug_is_on(self, settings, context):
        settings.DEBUG = True
        assert custom_exception_handler(RuntimeError("boom"), context) is None

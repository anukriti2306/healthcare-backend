"""Operational endpoints: health probe, API docs, JSON error handlers."""
from unittest.mock import MagicMock

import pytest
from django.db import OperationalError
from django.test import RequestFactory
from django.urls import reverse

from apps.core.views import not_found, server_error
from helpers import assert_error


class TestHealthCheck:
    def test_is_public_and_reports_database_up(self, anon_client):
        res = anon_client.get(reverse("health"))
        assert res.status_code == 200
        assert res.json() == {"status": "ok", "database": "up"}

    def test_ignores_a_bad_authorization_header(self, anon_client):
        anon_client.credentials(HTTP_AUTHORIZATION="Bearer garbage")
        assert anon_client.get(reverse("health")).status_code == 200

    def test_returns_503_when_the_database_is_down(self, anon_client, monkeypatch):
        broken = MagicMock()
        broken.cursor.side_effect = OperationalError("connection refused")
        monkeypatch.setattr("apps.core.views.connection", broken)
        res = anon_client.get(reverse("health"))
        assert res.status_code == 503
        assert res.json() == {"status": "degraded", "database": "down"}

    def test_failure_does_not_leak_the_database_error(self, anon_client, monkeypatch):
        broken = MagicMock()
        broken.cursor.side_effect = OperationalError("password authentication failed for user admin")
        monkeypatch.setattr("apps.core.views.connection", broken)
        assert "admin" not in anon_client.get(reverse("health")).content.decode()

    def test_only_get_is_allowed(self, anon_client):
        assert anon_client.post(reverse("health")).status_code == 405


class TestApiDocumentation:
    @pytest.fixture
    def schema(self, anon_client):
        res = anon_client.get(reverse("schema"), {"format": "json"})
        assert res.status_code == 200
        return res.json()

    def test_openapi_document_is_served_publicly(self, schema):
        assert schema["openapi"].startswith("3.")
        assert schema["info"]["title"] == "Healthcare Backend API"

    @pytest.mark.parametrize(
        ("path", "methods"),
        [
            ("/api/auth/register/", {"post"}),
            ("/api/auth/login/", {"post"}),
            ("/api/auth/token/refresh/", {"post"}),
            ("/api/auth/me/", {"get"}),
            ("/api/patients/", {"get", "post"}),
            ("/api/patients/{id}/", {"get", "put", "patch", "delete"}),
            ("/api/doctors/", {"get", "post"}),
            ("/api/doctors/{id}/", {"get", "put", "patch", "delete"}),
            ("/api/mappings/", {"get", "post"}),
            ("/api/mappings/{id}/", {"get", "delete"}),
            ("/api/health/", {"get"}),
        ],
    )
    def test_every_documented_endpoint_is_in_the_schema(self, schema, path, methods):
        assert path in schema["paths"]
        assert methods <= set(schema["paths"][path])

    def test_swagger_ui_is_served(self, anon_client):
        res = anon_client.get(reverse("docs"))
        assert res.status_code == 200
        assert b"swagger" in res.content.lower()


class TestJsonErrorHandlers:
    def test_not_found_handler(self):
        res = not_found(RequestFactory().get("/missing/"))
        assert res.status_code == 404
        assert b'"code": "not_found"' in res.content or b'"code":"not_found"' in res.content

    def test_server_error_handler_is_generic(self):
        res = server_error(RequestFactory().get("/boom/"))
        assert res.status_code == 500
        assert b"server_error" in res.content
        assert b"Traceback" not in res.content

    def test_handlers_are_wired_into_the_root_urlconf(self):
        import config.urls

        assert config.urls.handler404 == "apps.core.views.not_found"
        assert config.urls.handler500 == "apps.core.views.server_error"


def test_unexpected_exception_in_a_view_becomes_a_json_500(alice_client, monkeypatch, settings):
    settings.DEBUG = False
    monkeypatch.setattr(
        "apps.patients.views.PatientViewSet.get_queryset",
        MagicMock(side_effect=RuntimeError("kaboom with secrets")),
    )
    res = alice_client.get(reverse("patient-list"))
    assert_error(res, 500, "server_error")
    assert "kaboom" not in res.content.decode()

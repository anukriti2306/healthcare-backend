"""Whole-project guards: configuration, migrations and URL contract."""
import pytest
from django.core.management import call_command
from django.db import connection
from django.urls import resolve, reverse

pytestmark = pytest.mark.django_db


def test_django_system_checks_pass():
    call_command("check")


def test_models_and_migrations_are_in_sync():
    """Fails if someone changes a model but forgets to commit the migration."""
    call_command("makemigrations", check=True, dry_run=True, verbosity=0)


class TestSecureDefaults:
    def test_every_endpoint_requires_authentication_by_default(self, settings):
        assert settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"] == [
            "rest_framework.permissions.IsAuthenticated"
        ]

    def test_jwt_is_the_only_authentication_scheme(self, settings):
        assert settings.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"] == [
            "rest_framework_simplejwt.authentication.JWTAuthentication"
        ]

    def test_every_request_runs_in_a_transaction(self):
        assert connection.settings_dict["ATOMIC_REQUESTS"] is True

    def test_custom_user_model_is_active(self, settings):
        assert settings.AUTH_USER_MODEL == "accounts.User"

    def test_password_validators_are_enabled(self, settings):
        assert len(settings.AUTH_PASSWORD_VALIDATORS) >= 4

    def test_auth_endpoints_are_rate_limited(self, settings):
        assert "auth" in settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]

    def test_database_engine_is_postgresql(self):
        # The suite is meant to run against the production engine.
        assert connection.vendor == "postgresql"


@pytest.mark.parametrize(
    ("name", "kwargs", "path"),
    [
        ("auth-register", {}, "/api/auth/register/"),
        ("auth-login", {}, "/api/auth/login/"),
        ("auth-token-refresh", {}, "/api/auth/token/refresh/"),
        ("auth-me", {}, "/api/auth/me/"),
        ("patient-list", {}, "/api/patients/"),
        ("patient-detail", {"pk": 7}, "/api/patients/7/"),
        ("doctor-list", {}, "/api/doctors/"),
        ("doctor-detail", {"pk": 7}, "/api/doctors/7/"),
        ("mapping-list", {}, "/api/mappings/"),
        ("mapping-detail", {"pk": 7}, "/api/mappings/7/"),
        ("health", {}, "/api/health/"),
    ],
)
def test_url_contract_matches_the_assignment(name, kwargs, path):
    """The public paths are an API contract: renaming one must be deliberate."""
    assert reverse(name, kwargs=kwargs) == path
    assert resolve(path).url_name == name

"""Shared fixtures and automatic marker assignment."""
from pathlib import Path

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from tests.factories import DoctorFactory, MappingFactory, PatientFactory, UserFactory

_AUTO_MARKERS = {"unit": "unit", "api": "api", "integration": "integration"}


def pytest_collection_modifyitems(items):
    """Mark tests by directory; API/integration tests always need the database."""
    for item in items:
        folder = Path(str(item.fspath)).parent.name
        if folder in _AUTO_MARKERS:
            item.add_marker(getattr(pytest.mark, _AUTO_MARKERS[folder]))
        if folder in {"api", "integration"}:
            item.add_marker(pytest.mark.django_db)


@pytest.fixture(autouse=True)
def _isolate_test_environment(settings):
    """Per-test isolation: fresh throttle counters and a fast password hasher.

    Production keeps Django's default PBKDF2; hashing behaviour itself is covered
    by a dedicated test that restores the real hasher.
    """
    cache.clear()
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    yield
    cache.clear()


# --------------------------------------------------------------------------
# Clients
# --------------------------------------------------------------------------
def build_client(user=None):
    """An ``APIClient`` carrying a real JWT access token for ``user``."""
    client = APIClient()
    if user is not None:
        access = RefreshToken.for_user(user).access_token
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


@pytest.fixture
def anon_client():
    return build_client()


@pytest.fixture
def client_for():
    """Factory fixture: ``client_for(user)`` -> authenticated client."""
    return build_client


# --------------------------------------------------------------------------
# Users (two tenants, to prove isolation)
# --------------------------------------------------------------------------
@pytest.fixture
def alice(db):
    return UserFactory(email="alice@example.com", name="Alice")


@pytest.fixture
def bob(db):
    return UserFactory(email="bob@example.com", name="Bob")


@pytest.fixture
def alice_client(alice):
    return build_client(alice)


@pytest.fixture
def bob_client(bob):
    return build_client(bob)


# --------------------------------------------------------------------------
# Factories as fixtures, so tests never import them for simple cases
# --------------------------------------------------------------------------
@pytest.fixture
def user_factory(db):
    return UserFactory


@pytest.fixture
def patient_factory(db):
    return PatientFactory


@pytest.fixture
def doctor_factory(db):
    return DoctorFactory


@pytest.fixture
def mapping_factory(db):
    return MappingFactory

"""Shared helpers for the API tests."""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()

PASSWORD = "Str0ng!Pass#2026"


def make_user(email="alice@example.com", name="Alice", password=PASSWORD):
    return User.objects.create_user(email=email, name=name, password=password)


def client_for(user=None):
    """An APIClient authenticated with a real JWT access token for `user`."""
    client = APIClient()
    if user is not None:
        token = RefreshToken.for_user(user).access_token
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


# A fast hasher keeps the suite quick; production still uses Django's default
# (PBKDF2). Password *hashing* behaviour is covered by the register tests.
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class APITestBase(APITestCase):
    """Two users (alice, bob), each with an authenticated client."""

    def setUp(self):
        cache.clear()  # reset throttle counters between tests
        self.alice = make_user("alice@example.com", "Alice")
        self.bob = make_user("bob@example.com", "Bob")
        self.alice_client = client_for(self.alice)
        self.bob_client = client_for(self.bob)
        self.anon_client = client_for(None)

    def assertError(self, response, status_code, code=None):
        """Assert the response uses the standard error envelope."""
        self.assertEqual(response.status_code, status_code, response.content)
        body = response.json()
        self.assertIn("error", body)
        self.assertEqual(body["error"]["status"], status_code)
        if code is not None:
            self.assertEqual(body["error"]["code"], code)
        return body["error"]

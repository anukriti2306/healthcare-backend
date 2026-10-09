"""Registration, login, JWT lifecycle and rate limiting."""
import json
from datetime import timedelta

import jwt
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from helpers import PASSWORD, assert_error

User = get_user_model()

REGISTER = reverse("auth-register")
LOGIN = reverse("auth-login")
REFRESH = reverse("auth-token-refresh")
ME = reverse("auth-me")
PROTECTED = reverse("patient-list")


def register_payload(**overrides):
    data = {"name": "Carol", "email": "carol@example.com", "password": PASSWORD}
    data.update(overrides)
    return data


def bearer(client, token):
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


class TestRegister:
    def test_returns_user_and_a_working_token_pair(self, anon_client):
        res = anon_client.post(REGISTER, register_payload(), format="json")
        assert res.status_code == 201, res.content
        body = res.json()
        assert body["user"]["email"] == "carol@example.com"
        assert set(body["tokens"]) == {"access", "refresh"}
        # The freshly issued access token must work straight away.
        me = bearer(anon_client, body["tokens"]["access"]).get(ME)
        assert me.status_code == 200
        assert me.json()["id"] == body["user"]["id"]

    @pytest.mark.parametrize(
        ("raw", "stored"),
        [
            ("Carol@Example.COM", "carol@example.com"),
            ("  carol@example.com  ", "carol@example.com"),
        ],
    )
    def test_email_is_normalised(self, anon_client, raw, stored):
        res = anon_client.post(REGISTER, register_payload(email=raw), format="json")
        assert res.status_code == 201, res.content
        assert res.json()["user"]["email"] == stored
        assert User.objects.filter(email=stored).count() == 1

    def test_password_is_stored_hashed_with_the_production_hasher(self, anon_client, settings):
        settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.PBKDF2PasswordHasher"]
        anon_client.post(REGISTER, register_payload(), format="json")
        stored = User.objects.get(email="carol@example.com").password
        assert stored.startswith("pbkdf2_sha256$")
        assert PASSWORD not in stored

    def test_password_never_appears_in_any_response(self, anon_client):
        res = anon_client.post(REGISTER, register_payload(), format="json")
        assert PASSWORD not in res.content.decode()
        assert "password" not in res.json()["user"]

    def test_cannot_self_assign_staff_or_superuser(self, anon_client):
        """Mass-assignment guard: extra fields in the body must be ignored."""
        res = anon_client.post(
            REGISTER, register_payload(is_staff=True, is_superuser=True, is_active=False), format="json"
        )
        assert res.status_code == 201, res.content
        user = User.objects.get(email="carol@example.com")
        assert (user.is_staff, user.is_superuser, user.is_active) == (False, False, True)

    @pytest.mark.parametrize("field", ["name", "email", "password"])
    def test_each_field_is_required(self, anon_client, field):
        data = register_payload()
        del data[field]
        error = assert_error(anon_client.post(REGISTER, data, format="json"), 400, "validation_error")
        assert set(error["details"]) == {field}

    @pytest.mark.parametrize(
        ("overrides", "bad_field"),
        [
            pytest.param({"email": "not-an-email"}, "email", id="invalid-email"),
            pytest.param({"email": "a@b"}, "email", id="email-without-tld-dot"),
            pytest.param({"name": "   "}, "name", id="blank-name"),
            pytest.param({"name": "x" * 151}, "name", id="name-too-long"),
            pytest.param({"password": "short1!"}, "password", id="too-short"),
            pytest.param({"password": "12345678"}, "password", id="all-numeric"),
            pytest.param({"password": "password"}, "password", id="common-password"),
            pytest.param({"password": "carol@example.com"}, "password", id="similar-to-email"),
            pytest.param({"password": ""}, "password", id="empty-password"),
        ],
    )
    def test_invalid_input_is_rejected_and_nothing_is_created(self, anon_client, overrides, bad_field):
        res = anon_client.post(REGISTER, register_payload(**overrides), format="json")
        error = assert_error(res, 400, "validation_error")
        assert bad_field in error["details"]
        assert not User.objects.filter(email="carol@example.com").exists()

    def test_duplicate_email_is_rejected_case_insensitively(self, anon_client, alice):
        res = anon_client.post(REGISTER, register_payload(email="ALICE@example.com"), format="json")
        error = assert_error(res, 400, "validation_error")
        assert "email" in error["details"]
        assert User.objects.filter(email__iexact="alice@example.com").count() == 1

    def test_password_whitespace_is_significant(self, anon_client):
        """trim_whitespace=False: a password may legitimately start/end with spaces."""
        spaced = f" {PASSWORD} "
        assert anon_client.post(REGISTER, register_payload(password=spaced), format="json").status_code == 201
        assert anon_client.post(LOGIN, {"email": "carol@example.com", "password": spaced}, format="json").status_code == 200
        wrong = anon_client.post(LOGIN, {"email": "carol@example.com", "password": PASSWORD}, format="json")
        assert wrong.status_code == 401

    def test_stale_authorization_header_does_not_break_registration(self, anon_client):
        bearer(anon_client, "expired.or.garbage")
        assert anon_client.post(REGISTER, register_payload(), format="json").status_code == 201

    def test_get_is_not_allowed(self, anon_client):
        assert_error(anon_client.get(REGISTER), 405, "method_not_allowed")


class TestLogin:
    def test_returns_tokens_and_user(self, anon_client, alice):
        res = anon_client.post(LOGIN, {"email": "alice@example.com", "password": PASSWORD}, format="json")
        assert res.status_code == 200, res.content
        body = res.json()
        assert set(body) == {"access", "refresh", "user"}
        assert body["user"] == {"id": alice.id, "name": "Alice", "email": "alice@example.com",
                                "date_joined": body["user"]["date_joined"]}

    def test_access_token_carries_identity_claims(self, anon_client, alice):
        body = anon_client.post(LOGIN, {"email": "alice@example.com", "password": PASSWORD}, format="json").json()
        claims = AccessToken(body["access"])
        assert claims["user_id"] == str(alice.id)
        assert claims["email"] == "alice@example.com"
        assert claims["name"] == "Alice"
        assert claims["token_type"] == "access"

    def test_refresh_token_is_a_refresh_token(self, anon_client, alice):
        body = anon_client.post(LOGIN, {"email": "alice@example.com", "password": PASSWORD}, format="json").json()
        assert RefreshToken(body["refresh"])["token_type"] == "refresh"

    @pytest.mark.parametrize("email", ["ALICE@Example.com", "  alice@example.com  "])
    def test_email_is_case_and_whitespace_insensitive(self, anon_client, alice, email):
        res = anon_client.post(LOGIN, {"email": email, "password": PASSWORD}, format="json")
        assert res.status_code == 200, res.content

    def test_updates_last_login(self, anon_client, alice):
        assert alice.last_login is None
        anon_client.post(LOGIN, {"email": "alice@example.com", "password": PASSWORD}, format="json")
        alice.refresh_from_db()
        assert alice.last_login is not None

    def test_wrong_password_and_unknown_user_are_indistinguishable(self, anon_client, alice):
        """No user enumeration: both failures return the exact same error."""
        wrong = anon_client.post(LOGIN, {"email": "alice@example.com", "password": "Wrong-pass-1"}, format="json")
        ghost = anon_client.post(LOGIN, {"email": "ghost@example.com", "password": PASSWORD}, format="json")
        wrong_error = assert_error(wrong, 401, "no_active_account")
        ghost_error = assert_error(ghost, 401, "no_active_account")
        assert wrong_error == ghost_error

    def test_inactive_user_cannot_log_in(self, anon_client, alice):
        User.objects.filter(pk=alice.pk).update(is_active=False)
        res = anon_client.post(LOGIN, {"email": "alice@example.com", "password": PASSWORD}, format="json")
        assert_error(res, 401, "no_active_account")

    def test_missing_credentials(self, anon_client):
        error = assert_error(anon_client.post(LOGIN, {}, format="json"), 400, "validation_error")
        assert set(error["details"]) == {"email", "password"}

    def test_stale_authorization_header_does_not_break_login(self, anon_client, alice):
        bearer(anon_client, "expired.or.garbage")
        res = anon_client.post(LOGIN, {"email": "alice@example.com", "password": PASSWORD}, format="json")
        assert res.status_code == 200


class TestTokenRefresh:
    def test_exchanges_refresh_for_a_usable_access_token(self, anon_client, alice):
        refresh = str(RefreshToken.for_user(alice))
        res = anon_client.post(REFRESH, {"refresh": refresh}, format="json")
        assert res.status_code == 200, res.content
        assert bearer(anon_client, res.json()["access"]).get(ME).status_code == 200

    @pytest.mark.parametrize("token", ["nope", "", "a.b.c"])
    def test_rejects_malformed_refresh_tokens(self, anon_client, token):
        res = anon_client.post(REFRESH, {"refresh": token}, format="json")
        assert res.status_code in (400, 401)
        assert "error" in res.json()

    def test_access_token_cannot_be_used_as_a_refresh_token(self, anon_client, alice):
        access = str(RefreshToken.for_user(alice).access_token)
        assert_error(anon_client.post(REFRESH, {"refresh": access}, format="json"), 401, "token_not_valid")

    def test_missing_refresh_field(self, anon_client):
        error = assert_error(anon_client.post(REFRESH, {}, format="json"), 400, "validation_error")
        assert "refresh" in error["details"]


class TestAccessTokenEnforcement:
    """Every way a bearer token can be wrong must produce a clean 401."""

    def test_missing_token(self, anon_client):
        assert_error(anon_client.get(PROTECTED), 401, "not_authenticated")

    def test_unauthenticated_response_advertises_the_auth_scheme(self, anon_client):
        res = anon_client.get(PROTECTED)
        assert res["WWW-Authenticate"].startswith("Bearer")

    def test_garbage_token(self, anon_client):
        assert_error(bearer(anon_client, "garbage").get(PROTECTED), 401, "token_not_valid")

    def test_wrong_authorization_scheme(self, anon_client, alice):
        token = str(RefreshToken.for_user(alice).access_token)
        anon_client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        assert_error(anon_client.get(PROTECTED), 401, "not_authenticated")

    def test_refresh_token_is_not_accepted_as_an_access_token(self, anon_client, alice):
        refresh = str(RefreshToken.for_user(alice))
        assert_error(bearer(anon_client, refresh).get(PROTECTED), 401, "token_not_valid")

    def test_expired_token(self, anon_client, alice):
        token = AccessToken.for_user(alice)
        token.set_exp(lifetime=-timedelta(minutes=1))
        assert_error(bearer(anon_client, str(token)).get(PROTECTED), 401, "token_not_valid")

    def test_token_with_tampered_signature(self, anon_client, alice):
        token = str(AccessToken.for_user(alice))
        tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
        assert_error(bearer(anon_client, tampered).get(PROTECTED), 401, "token_not_valid")

    def test_token_signed_with_a_different_key(self, anon_client, alice):
        payload = AccessToken.for_user(alice).payload
        forged = jwt.encode(payload, "attacker-controlled-key", algorithm="HS256")
        assert_error(bearer(anon_client, forged).get(PROTECTED), 401, "token_not_valid")

    def test_unsigned_alg_none_token(self, anon_client, alice):
        """The classic JWT downgrade attack must be refused."""
        payload = AccessToken.for_user(alice).payload
        forged = jwt.encode(payload, key=None, algorithm="none")
        assert_error(bearer(anon_client, forged).get(PROTECTED), 401, "token_not_valid")

    def test_token_of_a_deleted_user(self, anon_client, alice):
        token = str(AccessToken.for_user(alice))
        alice.delete()
        assert_error(bearer(anon_client, token).get(PROTECTED), 401)

    def test_token_of_a_deactivated_user(self, anon_client, alice):
        token = str(AccessToken.for_user(alice))
        User.objects.filter(pk=alice.pk).update(is_active=False)
        assert_error(bearer(anon_client, token).get(PROTECTED), 401)


class TestMe:
    def test_returns_the_authenticated_user(self, alice_client, alice):
        res = alice_client.get(ME)
        assert res.status_code == 200
        assert res.json() == {"id": alice.id, "name": "Alice", "email": "alice@example.com",
                              "date_joined": res.json()["date_joined"]}

    @pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
    def test_is_read_only(self, alice_client, method):
        assert_error(getattr(alice_client, method)(ME, {}, format="json"), 405, "method_not_allowed")


class TestRateLimiting:
    @pytest.fixture(autouse=True)
    def _low_limit(self, monkeypatch):
        # DRF reads rates at class level; patch it for a fast, deterministic test.
        monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", {"auth": "3/min"})

    def test_login_is_throttled_after_the_limit(self, anon_client, alice):
        bad = {"email": "alice@example.com", "password": "Wrong-pass-1"}
        for _ in range(3):
            assert anon_client.post(LOGIN, bad, format="json").status_code == 401
        res = anon_client.post(LOGIN, bad, format="json")
        assert_error(res, 429, "throttled")
        assert int(res["Retry-After"]) > 0

    def test_throttling_blocks_even_correct_credentials(self, anon_client, alice):
        for _ in range(3):
            anon_client.post(LOGIN, {"email": "alice@example.com", "password": "Wrong-pass-1"}, format="json")
        good = anon_client.post(LOGIN, {"email": "alice@example.com", "password": PASSWORD}, format="json")
        assert good.status_code == 429

    def test_register_and_refresh_share_the_auth_scope(self, anon_client):
        for i in range(3):
            anon_client.post(REGISTER, register_payload(email=f"u{i}@example.com"), format="json")
        assert anon_client.post(REFRESH, {"refresh": "x"}, format="json").status_code == 429

    def test_regular_endpoints_are_not_throttled_by_the_auth_scope(self, alice_client):
        for _ in range(10):
            assert alice_client.get(PROTECTED).status_code == 200


def test_error_bodies_are_valid_json_with_correct_content_type(anon_client):
    res = anon_client.get(PROTECTED)
    assert res["Content-Type"].startswith("application/json")
    json.loads(res.content)

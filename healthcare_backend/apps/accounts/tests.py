from django.contrib.auth import get_user_model

from apps.core.testing import PASSWORD, APITestBase, client_for

User = get_user_model()

REGISTER = "/api/auth/register/"
LOGIN = "/api/auth/login/"
REFRESH = "/api/auth/token/refresh/"


class RegisterTests(APITestBase):
    def test_register_success_returns_user_and_tokens(self):
        res = self.anon_client.post(
            REGISTER,
            {"name": "Carol", "email": "carol@example.com", "password": PASSWORD},
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.content)
        body = res.json()
        self.assertEqual(body["user"]["email"], "carol@example.com")
        self.assertEqual(body["user"]["name"], "Carol")
        self.assertIn("access", body["tokens"])
        self.assertIn("refresh", body["tokens"])
        self.assertNotIn("password", body["user"])

    def test_password_is_hashed(self):
        self.anon_client.post(
            REGISTER,
            {"name": "Carol", "email": "carol@example.com", "password": PASSWORD},
            format="json",
        )
        user = User.objects.get(email="carol@example.com")
        self.assertNotEqual(user.password, PASSWORD)
        self.assertTrue(user.check_password(PASSWORD))

    def test_email_is_normalised_to_lowercase(self):
        res = self.anon_client.post(
            REGISTER,
            {"name": "Carol", "email": "  Carol@Example.COM ", "password": PASSWORD},
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.json()["user"]["email"], "carol@example.com")

    def test_duplicate_email_rejected_case_insensitively(self):
        res = self.anon_client.post(
            REGISTER,
            {"name": "Imposter", "email": "ALICE@example.com", "password": PASSWORD},
            format="json",
        )
        error = self.assertError(res, 400, "validation_error")
        self.assertIn("email", error["details"])

    def test_missing_fields(self):
        res = self.anon_client.post(REGISTER, {}, format="json")
        error = self.assertError(res, 400, "validation_error")
        self.assertEqual(set(error["details"]), {"name", "email", "password"})

    def test_invalid_email(self):
        res = self.anon_client.post(
            REGISTER, {"name": "X", "email": "not-an-email", "password": PASSWORD}, format="json"
        )
        error = self.assertError(res, 400, "validation_error")
        self.assertIn("email", error["details"])

    def test_blank_name_rejected(self):
        res = self.anon_client.post(
            REGISTER, {"name": "   ", "email": "x@example.com", "password": PASSWORD}, format="json"
        )
        error = self.assertError(res, 400, "validation_error")
        self.assertIn("name", error["details"])

    def test_weak_passwords_rejected(self):
        for weak in ["short1!", "12345678", "password", "carol@example.com"]:
            with self.subTest(password=weak):
                res = self.anon_client.post(
                    REGISTER,
                    {"name": "Carol", "email": "carol@example.com", "password": weak},
                    format="json",
                )
                error = self.assertError(res, 400, "validation_error")
                self.assertIn("password", error["details"])
        self.assertFalse(User.objects.filter(email="carol@example.com").exists())

    def test_malformed_json_returns_400(self):
        res = self.anon_client.post(REGISTER, "{not json", content_type="application/json")
        self.assertError(res, 400, "parse_error")

    def test_invalid_authorization_header_does_not_block_register(self):
        client = client_for(None)
        client.credentials(HTTP_AUTHORIZATION="Bearer garbage")
        res = client.post(
            REGISTER,
            {"name": "Carol", "email": "carol@example.com", "password": PASSWORD},
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.content)


class LoginTests(APITestBase):
    def test_login_success(self):
        res = self.anon_client.post(
            LOGIN, {"email": "alice@example.com", "password": PASSWORD}, format="json"
        )
        self.assertEqual(res.status_code, 200, res.content)
        body = res.json()
        self.assertIn("access", body)
        self.assertIn("refresh", body)
        self.assertEqual(body["user"]["email"], "alice@example.com")

    def test_access_token_works_on_protected_endpoint(self):
        body = self.anon_client.post(
            LOGIN, {"email": "alice@example.com", "password": PASSWORD}, format="json"
        ).json()
        client = client_for(None)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {body['access']}")
        self.assertEqual(client.get("/api/patients/").status_code, 200)
        self.assertEqual(client.get("/api/auth/me/").json()["email"], "alice@example.com")

    def test_login_email_is_case_insensitive(self):
        res = self.anon_client.post(
            LOGIN, {"email": "ALICE@Example.com", "password": PASSWORD}, format="json"
        )
        self.assertEqual(res.status_code, 200, res.content)

    def test_login_updates_last_login(self):
        self.assertIsNone(User.objects.get(pk=self.alice.pk).last_login)
        self.anon_client.post(
            LOGIN, {"email": "alice@example.com", "password": PASSWORD}, format="json"
        )
        self.assertIsNotNone(User.objects.get(pk=self.alice.pk).last_login)

    def test_wrong_password(self):
        res = self.anon_client.post(
            LOGIN, {"email": "alice@example.com", "password": "Wrong-pass-1"}, format="json"
        )
        self.assertError(res, 401, "no_active_account")

    def test_unknown_user_gets_same_error_as_wrong_password(self):
        res = self.anon_client.post(
            LOGIN, {"email": "ghost@example.com", "password": PASSWORD}, format="json"
        )
        self.assertError(res, 401, "no_active_account")

    def test_inactive_user_cannot_login(self):
        User.objects.filter(pk=self.alice.pk).update(is_active=False)
        res = self.anon_client.post(
            LOGIN, {"email": "alice@example.com", "password": PASSWORD}, format="json"
        )
        self.assertError(res, 401)

    def test_missing_credentials(self):
        res = self.anon_client.post(LOGIN, {}, format="json")
        error = self.assertError(res, 400, "validation_error")
        self.assertEqual(set(error["details"]), {"email", "password"})

    def test_invalid_authorization_header_does_not_block_login(self):
        client = client_for(None)
        client.credentials(HTTP_AUTHORIZATION="Bearer expired-or-garbage")
        res = client.post(LOGIN, {"email": "alice@example.com", "password": PASSWORD}, format="json")
        self.assertEqual(res.status_code, 200, res.content)


class TokenTests(APITestBase):
    def test_refresh_returns_new_access_token(self):
        login = self.anon_client.post(
            LOGIN, {"email": "alice@example.com", "password": PASSWORD}, format="json"
        ).json()
        res = self.anon_client.post(REFRESH, {"refresh": login["refresh"]}, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertIn("access", res.json())

    def test_refresh_with_invalid_token(self):
        res = self.anon_client.post(REFRESH, {"refresh": "nope"}, format="json")
        self.assertError(res, 401, "token_not_valid")

    def test_refresh_token_cannot_be_used_as_access_token(self):
        login = self.anon_client.post(
            LOGIN, {"email": "alice@example.com", "password": PASSWORD}, format="json"
        ).json()
        client = client_for(None)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {login['refresh']}")
        self.assertError(client.get("/api/patients/"), 401, "token_not_valid")

    def test_missing_token_returns_401(self):
        res = self.anon_client.get("/api/patients/")
        self.assertError(res, 401, "not_authenticated")

    def test_garbage_token_returns_401(self):
        client = client_for(None)
        client.credentials(HTTP_AUTHORIZATION="Bearer garbage")
        self.assertError(client.get("/api/patients/"), 401, "token_not_valid")

    def test_every_protected_endpoint_requires_auth(self):
        endpoints = [
            ("get", "/api/auth/me/"),
            ("get", "/api/patients/"),
            ("post", "/api/patients/"),
            ("get", "/api/patients/1/"),
            ("put", "/api/patients/1/"),
            ("delete", "/api/patients/1/"),
            ("get", "/api/doctors/"),
            ("post", "/api/doctors/"),
            ("get", "/api/doctors/1/"),
            ("put", "/api/doctors/1/"),
            ("delete", "/api/doctors/1/"),
            ("get", "/api/mappings/"),
            ("post", "/api/mappings/"),
            ("get", "/api/mappings/1/"),
            ("delete", "/api/mappings/1/"),
        ]
        for method, url in endpoints:
            with self.subTest(method=method, url=url):
                res = getattr(self.anon_client, method)(url, {}, format="json")
                self.assertError(res, 401)


class MiscTests(APITestBase):
    def test_health_check_is_public(self):
        res = self.anon_client.get("/api/health/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "ok", "database": "up"})

    def test_openapi_schema_is_generated(self):
        res = self.anon_client.get("/api/schema/")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"/api/patients/", res.content)
        self.assertIn(b"/api/mappings/{id}/", res.content)

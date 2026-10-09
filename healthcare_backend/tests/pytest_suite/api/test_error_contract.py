"""
The API promises ONE error shape. These tests drive many different failure
modes through the real stack and assert that every one honours the envelope.
"""
import pytest
from django.urls import reverse

from helpers import assert_error, patient_payload

SCENARIOS = [
    pytest.param("get", "/api/patients/", None, "anon", 401, "not_authenticated", id="no-token"),
    pytest.param("get", "/api/patients/999999/", None, "alice", 404, "not_found", id="unknown-patient"),
    pytest.param("get", "/api/patients/not-a-number/", None, "alice", 404, "not_found", id="bad-url-pattern"),
    pytest.param("get", "/api/this/route/does/not/exist/", None, "alice", 404, "not_found", id="unknown-route"),
    pytest.param("get", "/api/this/route/does/not/exist/", None, "anon", 404, "not_found", id="unknown-route-anon"),
    pytest.param("post", "/api/patients/", {}, "alice", 400, "validation_error", id="empty-body"),
    pytest.param("post", "/api/patients/", patient_payload(age=-1), "alice", 400, "validation_error", id="bad-age"),
    pytest.param("put", "/api/patients/", {}, "alice", 405, "method_not_allowed", id="wrong-method"),
    pytest.param("delete", "/api/auth/me/", None, "alice", 405, "method_not_allowed", id="wrong-method-me"),
    pytest.param("get", "/api/patients/?min_age=abc", None, "alice", 400, "validation_error", id="bad-filter"),
    pytest.param("post", "/api/mappings/", {"patient": 1, "doctor": 1}, "alice", 400, "validation_error",
                 id="mapping-unknown-ids"),
    pytest.param("delete", "/api/mappings/999999/", None, "alice", 404, "not_found", id="unknown-mapping"),
    pytest.param("post", "/api/auth/login/", {"email": "x@example.com", "password": "nope-Nope-1"}, "anon", 401,
                 "no_active_account", id="bad-login"),
]


@pytest.mark.parametrize(("method", "url", "body", "who", "status", "code"), SCENARIOS)
def test_every_failure_uses_the_same_envelope(method, url, body, who, status, code, alice_client, anon_client):
    client = alice_client if who == "alice" else anon_client
    res = getattr(client, method)(url, body, format="json")
    assert_error(res, status, code)
    assert res["Content-Type"].startswith("application/json")


def test_unknown_routes_return_json_not_html(anon_client):
    res = anon_client.get("/definitely/not/here/")
    assert res.status_code == 404
    assert res["Content-Type"].startswith("application/json")
    assert_error(res, 404, "not_found")


def test_validation_details_are_keyed_by_field(alice_client):
    error = assert_error(alice_client.post(reverse("patient-list"), {"name": "", "age": "x"}, format="json"),
                         400, "validation_error")
    assert set(error["details"]) == {"name", "age"}
    assert all(isinstance(messages, list) and messages for messages in error["details"].values())


def test_error_status_in_body_always_matches_the_http_status(alice_client):
    for url in ("/api/patients/999999/", "/api/patients/abc/", "/api/nope/"):
        res = alice_client.get(url)
        assert res.json()["error"]["status"] == res.status_code

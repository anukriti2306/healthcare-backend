#!/usr/bin/env python
"""
End-to-end smoke test against a *running* server (standard library only).

    python scripts/smoke_test.py                      # http://127.0.0.1:8000
    python scripts/smoke_test.py http://localhost:8000

It registers a throw-away user, walks through every endpoint in the assignment
and prints PASS/FAIL per step. Exits with status 1 if anything fails.
"""
import json
import sys
import time
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
PASSWORD = "Str0ng!Pass#2026"
failures = 0


def call(method, path, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return exc.code, (json.loads(raw) if raw else None)


def check(label, got_status, expected_status, extra_ok=True):
    global failures
    ok = got_status == expected_status and extra_ok
    failures += 0 if ok else 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}  (HTTP {got_status}, expected {expected_status})")


def main():
    email = f"smoke_{int(time.time() * 1000)}@example.com"
    print(f"Smoke testing {BASE} as {email}\n")

    status, body = call("GET", "/api/health/")
    check("health check", status, 200, body == {"status": "ok", "database": "up"})

    print("\nAuthentication")
    status, body = call("POST", "/api/auth/register/", {"name": "Smoke Tester", "email": email, "password": PASSWORD})
    check("register", status, 201, "access" in (body or {}).get("tokens", {}))
    status, body = call("POST", "/api/auth/register/", {"name": "Dup", "email": email, "password": PASSWORD})
    check("register duplicate email is rejected", status, 400)
    status, body = call("POST", "/api/auth/login/", {"email": email, "password": "wrong-Pass-1"})
    check("login with wrong password is rejected", status, 401)
    status, body = call("POST", "/api/auth/login/", {"email": email, "password": PASSWORD})
    check("login", status, 200, "access" in (body or {}))
    token = body["access"]
    status, _ = call("GET", "/api/patients/")
    check("protected endpoint without token is rejected", status, 401)

    print("\nPatients")
    status, patient = call("POST", "/api/patients/", {"name": "John Doe", "age": 42, "gender": "male"}, token)
    check("create patient", status, 201)
    pid = patient["id"]
    status, body = call("GET", "/api/patients/", token=token)
    check("list patients", status, 200, any(p["id"] == pid for p in body))
    status, body = call("GET", f"/api/patients/{pid}/", token=token)
    check("get patient", status, 200, body["name"] == "John Doe")
    status, body = call("PUT", f"/api/patients/{pid}/", {"name": "John Updated", "age": 43, "gender": "male"}, token)
    check("update patient", status, 200, body["name"] == "John Updated")
    status, _ = call("POST", "/api/patients/", {"name": "", "age": -1}, token)
    check("invalid patient is rejected", status, 400)

    print("\nDoctors")
    status, doctor = call("POST", "/api/doctors/", {"name": "Dr. Asha Rao", "specialization": "Cardiology"}, token)
    check("create doctor", status, 201)
    did = doctor["id"]
    status, body = call("GET", "/api/doctors/", token=token)
    check("list doctors", status, 200, any(d["id"] == did for d in body))
    status, body = call("GET", f"/api/doctors/{did}/", token=token)
    check("get doctor", status, 200)
    status, body = call("PUT", f"/api/doctors/{did}/", {"name": "Dr. Asha Rao", "specialization": "Neurology"}, token)
    check("update doctor", status, 200, body["specialization"] == "Neurology")

    print("\nMappings")
    status, mapping = call("POST", "/api/mappings/", {"patient": pid, "doctor": did}, token)
    check("assign doctor to patient", status, 201)
    mid = mapping["id"]
    status, _ = call("POST", "/api/mappings/", {"patient": pid, "doctor": did}, token)
    check("duplicate assignment is rejected", status, 400)
    status, body = call("GET", "/api/mappings/", token=token)
    check("list mappings", status, 200, any(m["id"] == mid for m in body))
    status, body = call("GET", f"/api/mappings/{pid}/", token=token)
    check("doctors of a patient", status, 200, body[0]["doctor"]["id"] == did)
    status, _ = call("DELETE", f"/api/mappings/{mid}/", token=token)
    check("remove doctor from patient", status, 204)
    status, body = call("GET", f"/api/mappings/{pid}/", token=token)
    check("patient has no doctors afterwards", status, 200, body == [])

    print("\nCleanup")
    status, _ = call("DELETE", f"/api/doctors/{did}/", token=token)
    check("delete doctor", status, 204)
    status, _ = call("DELETE", f"/api/patients/{pid}/", token=token)
    check("delete patient", status, 204)
    status, _ = call("GET", f"/api/patients/{pid}/", token=token)
    check("deleted patient is gone", status, 404)

    print(f"\n{'ALL CHECKS PASSED' if not failures else f'{failures} CHECK(S) FAILED'}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()

"""End-to-end scenarios through the public API only (no ORM shortcuts)."""
import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from tests.helpers import PASSWORD, assert_error, doctor_payload, patient_payload


def authed(access):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def sign_up(email, name):
    res = APIClient().post(reverse("auth-register"), {"name": name, "email": email, "password": PASSWORD}, format="json")
    assert res.status_code == 201, res.content
    return res.json()


def test_new_clinician_journey_from_signup_to_cleanup():
    """Register -> log in -> add patient & doctor -> assign -> review -> unassign -> delete."""
    sign_up("dr.demo@example.com", "Dr Demo")

    login = APIClient().post(reverse("auth-login"), {"email": "dr.demo@example.com", "password": PASSWORD},
                             format="json").json()
    api = authed(login["access"])

    patient = api.post(reverse("patient-list"), patient_payload(name="Ravi", age=51), format="json").json()
    doctor = api.post(reverse("doctor-list"), doctor_payload(name="Dr. Meera", specialization="Oncology"),
                      format="json").json()

    mapping = api.post(reverse("mapping-list"), {"patient": patient["id"], "doctor": doctor["id"]},
                       format="json").json()
    assert api.get(reverse("mapping-list")).json()[0]["id"] == mapping["id"]

    assigned = api.get(reverse("mapping-detail", kwargs={"pk": patient["id"]})).json()
    assert [a["doctor"]["id"] for a in assigned] == [doctor["id"]]
    assert assigned[0]["id"] == mapping["id"], "list item id must be usable for DELETE"

    assert api.delete(reverse("mapping-detail", kwargs={"pk": mapping["id"]})).status_code == 204
    assert api.get(reverse("mapping-detail", kwargs={"pk": patient["id"]})).json() == []

    assert api.delete(reverse("patient-detail", kwargs={"pk": patient["id"]})).status_code == 204
    assert api.get(reverse("patient-list")).json() == []
    # The doctor directory entry outlives the patient.
    assert api.get(reverse("doctor-detail", kwargs={"pk": doctor["id"]})).status_code == 200


def test_token_refresh_keeps_a_session_alive():
    tokens = sign_up("session@example.com", "Session")["tokens"]
    refreshed = APIClient().post(reverse("auth-token-refresh"), {"refresh": tokens["refresh"]}, format="json").json()
    assert authed(refreshed["access"]).get(reverse("auth-me")).json()["email"] == "session@example.com"


def test_two_clinicians_share_doctors_but_never_patients():
    alice = authed(sign_up("alice.flow@example.com", "Alice")["tokens"]["access"])
    bob = authed(sign_up("bob.flow@example.com", "Bob")["tokens"]["access"])

    shared_doctor = alice.post(reverse("doctor-list"), doctor_payload(email="shared@hospital.com"), format="json").json()
    alices_patient = alice.post(reverse("patient-list"), patient_payload(name="Alice's"), format="json").json()
    bobs_patient = bob.post(reverse("patient-list"), patient_payload(name="Bob's"), format="json").json()

    # Bob sees Alice's doctor and can assign them to his own patient...
    assert bob.get(reverse("doctor-detail", kwargs={"pk": shared_doctor["id"]})).status_code == 200
    res = bob.post(reverse("mapping-list"), {"patient": bobs_patient["id"], "doctor": shared_doctor["id"]},
                   format="json")
    assert res.status_code == 201

    # ...but cannot edit that doctor, nor touch Alice's patient or assign to it.
    assert_error(bob.patch(reverse("doctor-detail", kwargs={"pk": shared_doctor["id"]}), {"name": "X"},
                           format="json"), 403, "permission_denied")
    assert_error(bob.get(reverse("patient-detail", kwargs={"pk": alices_patient["id"]})), 404, "not_found")
    res = bob.post(reverse("mapping-list"), {"patient": alices_patient["id"], "doctor": shared_doctor["id"]},
                   format="json")
    assert res.status_code == 400

    # Each clinician's mapping list shows only their own assignments.
    assert alice.get(reverse("mapping-list")).json() == []
    assert len(bob.get(reverse("mapping-list")).json()) == 1


def test_deleting_a_doctor_clears_assignments_for_all_patients():
    alice = authed(sign_up("cascade@example.com", "Cascade")["tokens"]["access"])
    doctor = alice.post(reverse("doctor-list"), doctor_payload(email=""), format="json").json()
    patient_ids = []
    for n in range(3):
        p = alice.post(reverse("patient-list"), patient_payload(name=f"P{n}"), format="json").json()
        patient_ids.append(p["id"])
        alice.post(reverse("mapping-list"), {"patient": p["id"], "doctor": doctor["id"]}, format="json")
    assert len(alice.get(reverse("mapping-list")).json()) == 3

    assert alice.delete(reverse("doctor-detail", kwargs={"pk": doctor["id"]})).status_code == 204

    assert alice.get(reverse("mapping-list")).json() == []
    assert len(alice.get(reverse("patient-list")).json()) == 3


@pytest.mark.parametrize("step", ["register", "login"])
def test_bad_credentials_never_yield_tokens(step):
    sign_up("exists@example.com", "Exists")
    client = APIClient()
    if step == "register":
        res = client.post(reverse("auth-register"),
                          {"name": "Imposter", "email": "EXISTS@example.com", "password": PASSWORD}, format="json")
    else:
        res = client.post(reverse("auth-login"), {"email": "exists@example.com", "password": "Wrong-pass-1"},
                          format="json")
    assert res.status_code in (400, 401)
    assert "access" not in res.content.decode()

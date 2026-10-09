"""
Cross-cutting security properties, expressed as parametrized matrices so that
adding an endpoint without protecting it shows up as a failing test case.
"""
import pytest
from django.urls import reverse

from apps.doctors.models import Doctor
from apps.mappings.models import PatientDoctorMapping
from apps.patients.models import Patient
from helpers import assert_error, doctor_payload, patient_payload

ENDPOINTS = [
    ("get", "auth-me", None, None),
    ("get", "patient-list", None, None),
    ("post", "patient-list", None, patient_payload()),
    ("get", "patient-detail", 1, None),
    ("put", "patient-detail", 1, patient_payload()),
    ("patch", "patient-detail", 1, {}),
    ("delete", "patient-detail", 1, None),
    ("get", "doctor-list", None, None),
    ("post", "doctor-list", None, doctor_payload()),
    ("get", "doctor-detail", 1, None),
    ("put", "doctor-detail", 1, doctor_payload()),
    ("patch", "doctor-detail", 1, {}),
    ("delete", "doctor-detail", 1, None),
    ("get", "mapping-list", None, None),
    ("post", "mapping-list", None, {"patient": 1, "doctor": 1}),
    ("get", "mapping-detail", 1, None),
    ("delete", "mapping-detail", 1, None),
]


def url_for(name, pk):
    return reverse(name, kwargs={"pk": pk}) if pk is not None else reverse(name)


@pytest.mark.parametrize(
    ("method", "name", "pk", "body"),
    ENDPOINTS,
    ids=[f"{m.upper()} {n}" for m, n, _, _ in ENDPOINTS],
)
def test_every_protected_endpoint_rejects_anonymous_requests(anon_client, method, name, pk, body):
    res = getattr(anon_client, method)(url_for(name, pk), body, format="json")
    assert_error(res, 401, "not_authenticated")


def test_anonymous_requests_never_create_data(anon_client):
    anon_client.post(reverse("patient-list"), patient_payload(), format="json")
    anon_client.post(reverse("doctor-list"), doctor_payload(), format="json")
    assert (Patient.objects.count(), Doctor.objects.count()) == (0, 0)


class TestTenantIsolation:
    """Alice must be unable to read or change anything of Bob's patients."""

    @pytest.fixture
    def bobs(self, bob, patient_factory, doctor_factory, mapping_factory):
        patient = patient_factory(name="Bob's Secret Patient", medical_history="confidential", created_by=bob)
        mapping = mapping_factory(patient=patient, doctor=doctor_factory(created_by=bob))
        return {"patient": patient, "mapping": mapping}

    @pytest.mark.parametrize("method", ["get", "put", "patch", "delete"])
    def test_patient_detail_is_invisible_to_other_users(self, alice_client, bobs, method):
        body = patient_payload() if method in {"put", "patch"} else None
        res = getattr(alice_client, method)(url_for("patient-detail", bobs["patient"].id), body, format="json")
        assert_error(res, 404, "not_found")
        bobs["patient"].refresh_from_db()
        assert bobs["patient"].medical_history == "confidential"

    def test_other_users_data_never_appears_in_any_list(self, alice_client, bobs):
        for name in ("patient-list", "mapping-list"):
            body = alice_client.get(reverse(name)).content.decode()
            assert "Bob's Secret Patient" not in body
        assert alice_client.get(reverse("patient-list")).json() == []
        assert alice_client.get(reverse("mapping-list")).json() == []

    def test_other_users_mapping_cannot_be_read_or_deleted(self, alice_client, bobs):
        assert_error(alice_client.get(url_for("mapping-detail", bobs["patient"].id)), 404, "not_found")
        assert_error(alice_client.delete(url_for("mapping-detail", bobs["mapping"].id)), 404, "not_found")
        assert PatientDoctorMapping.objects.filter(pk=bobs["mapping"].id).exists()

    def test_not_found_and_forbidden_are_indistinguishable_for_patients(self, alice_client, bobs):
        """404 for 'exists but not yours' must equal 404 for 'does not exist'."""
        foreign = alice_client.get(url_for("patient-detail", bobs["patient"].id))
        missing = alice_client.get(url_for("patient-detail", 999_999))
        assert foreign.status_code == missing.status_code == 404
        assert foreign.json() == missing.json()

    def test_a_forged_created_by_cannot_smuggle_a_patient_into_another_account(self, alice_client, alice, bob):
        res = alice_client.post(reverse("patient-list"), patient_payload(created_by=bob.id), format="json")
        assert res.json()["created_by"] == alice.id
        assert Patient.objects.filter(created_by=bob).count() == 0


class TestSensitiveDataExposure:
    def test_no_endpoint_returns_password_material(self, alice_client, alice):
        for name in ("auth-me", "patient-list", "doctor-list", "mapping-list"):
            content = alice_client.get(reverse(name)).content.decode()
            assert alice.password not in content
            assert "pbkdf2" not in content and "md5$" not in content

    def test_server_errors_do_not_leak_internals(self, alice_client, monkeypatch, settings):
        settings.DEBUG = False
        from apps.patients.views import PatientViewSet

        def explode(*args, **kwargs):
            raise RuntimeError("secret connection string postgres://admin:hunter2@db")

        monkeypatch.setattr(PatientViewSet, "list", explode)
        res = alice_client.get(reverse("patient-list"))
        error = assert_error(res, 500, "server_error")
        body = res.content.decode()
        assert "hunter2" not in body and "Traceback" not in body and "RuntimeError" not in body
        assert error["message"]

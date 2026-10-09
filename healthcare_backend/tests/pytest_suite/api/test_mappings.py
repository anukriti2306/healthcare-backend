"""Patient <-> doctor mappings API."""
import pytest
from django.db import connection
from django.urls import reverse
from rest_framework.exceptions import ValidationError

from apps.doctors.models import Doctor
from apps.mappings.models import PatientDoctorMapping
from apps.mappings.serializers import MappingSerializer
from apps.patients.models import Patient
from helpers import assert_error

LIST = reverse("mapping-list")


def detail(pk):
    return reverse("mapping-detail", kwargs={"pk": pk})


@pytest.fixture
def world(alice, bob, patient_factory, doctor_factory):
    """Alice owns two patients; Bob owns one; two doctors exist (one per user)."""
    return {
        "patient": patient_factory(name="Alice's Patient", created_by=alice),
        "patient2": patient_factory(name="Alice's Patient 2", created_by=alice),
        "bobs_patient": patient_factory(name="Bob's Patient", created_by=bob),
        "cardio": doctor_factory(name="Dr. Cardio", specialization="Cardiology", created_by=alice),
        "neuro": doctor_factory(name="Dr. Neuro", specialization="Neurology", created_by=bob),
    }


def assign(client, patient, doctor):
    return client.post(LIST, {"patient": patient.id, "doctor": doctor.id}, format="json")


class TestAssign:
    def test_assigns_a_doctor_to_a_patient(self, alice_client, world):
        res = assign(alice_client, world["patient"], world["cardio"])
        assert res.status_code == 201, res.content
        body = res.json()
        assert body["patient"] == world["patient"].id
        assert body["doctor"] == world["cardio"].id
        assert body["patient_name"] == "Alice's Patient"
        assert body["doctor_name"] == "Dr. Cardio"
        assert body["doctor_specialization"] == "Cardiology"

    def test_can_assign_a_doctor_created_by_someone_else(self, alice_client, world):
        """Doctors are a shared directory, so any user may assign any doctor."""
        assert assign(alice_client, world["patient"], world["neuro"]).status_code == 201

    def test_one_doctor_can_serve_many_patients_and_vice_versa(self, alice_client, world):
        for patient, doctor in [("patient", "cardio"), ("patient2", "cardio"), ("patient", "neuro")]:
            assert assign(alice_client, world[patient], world[doctor]).status_code == 201
        assert PatientDoctorMapping.objects.count() == 3

    def test_duplicate_assignment_is_rejected(self, alice_client, world):
        assign(alice_client, world["patient"], world["cardio"])
        error = assert_error(assign(alice_client, world["patient"], world["cardio"]), 400, "validation_error")
        assert "already assigned" in str(error["details"])
        assert PatientDoctorMapping.objects.count() == 1

    def test_cannot_assign_to_another_users_patient(self, alice_client, world):
        error = assert_error(assign(alice_client, world["bobs_patient"], world["cardio"]), 400, "validation_error")
        # Same message as a nonexistent patient: ids of other tenants are not revealed.
        assert error["details"]["patient"] == ["Patient not found."]
        assert PatientDoctorMapping.objects.count() == 0

    def test_foreign_and_nonexistent_patients_are_indistinguishable(self, alice_client, world):
        foreign = alice_client.post(LIST, {"patient": world["bobs_patient"].id, "doctor": world["cardio"].id},
                                    format="json").json()
        missing = alice_client.post(LIST, {"patient": 999_999, "doctor": world["cardio"].id}, format="json").json()
        assert foreign == missing

    def test_unknown_doctor(self, alice_client, world):
        res = alice_client.post(LIST, {"patient": world["patient"].id, "doctor": 999_999}, format="json")
        assert assert_error(res, 400)["details"]["doctor"] == ["Doctor not found."]

    @pytest.mark.parametrize(
        "body",
        [
            pytest.param({}, id="empty"),
            pytest.param({"patient": "abc", "doctor": "xyz"}, id="non-numeric"),
            pytest.param({"patient": None, "doctor": None}, id="nulls"),
            pytest.param({"patient": [1], "doctor": [2]}, id="lists"),
            pytest.param({"patient": -1, "doctor": 0}, id="non-positive"),
        ],
    )
    def test_malformed_bodies_are_rejected_cleanly(self, alice_client, body):
        error = assert_error(alice_client.post(LIST, body, format="json"), 400, "validation_error")
        assert set(error["details"]) == {"patient", "doctor"}

    def test_read_only_response_fields_cannot_be_forged(self, alice_client, world):
        res = alice_client.post(
            LIST,
            {"patient": world["patient"].id, "doctor": world["cardio"].id, "id": 999_999,
             "doctor_name": "Forged", "created_at": "2000-01-01T00:00:00Z"},
            format="json",
        )
        body = res.json()
        assert body["id"] != 999_999
        assert body["doctor_name"] == "Dr. Cardio"

    def test_put_and_patch_are_not_available(self, alice_client, world):
        mapping = PatientDoctorMapping.objects.create(patient=world["patient"], doctor=world["cardio"])
        assert_error(alice_client.put(detail(mapping.id), {}, format="json"), 405, "method_not_allowed")
        assert_error(alice_client.patch(detail(mapping.id), {}, format="json"), 405, "method_not_allowed")

    def test_post_to_the_detail_url_is_not_allowed(self, alice_client, world):
        assert_error(alice_client.post(detail(world["patient"].id), {}, format="json"), 405, "method_not_allowed")


class TestListAndDoctorsOfPatient:
    @pytest.fixture
    def mappings(self, world):
        return {
            "m1": PatientDoctorMapping.objects.create(patient=world["patient"], doctor=world["cardio"]),
            "m2": PatientDoctorMapping.objects.create(patient=world["patient"], doctor=world["neuro"]),
            "m3": PatientDoctorMapping.objects.create(patient=world["patient2"], doctor=world["cardio"]),
            "bobs": PatientDoctorMapping.objects.create(patient=world["bobs_patient"], doctor=world["cardio"]),
        }

    def test_list_returns_only_mappings_of_own_patients(self, alice_client, mappings):
        body = alice_client.get(LIST).json()
        assert isinstance(body, list)
        assert {m["id"] for m in body} == {mappings["m1"].id, mappings["m2"].id, mappings["m3"].id}

    def test_list_is_newest_first(self, alice_client, mappings):
        ids = [m["id"] for m in alice_client.get(LIST).json()]
        assert ids == [mappings["m3"].id, mappings["m2"].id, mappings["m1"].id]

    @pytest.mark.parametrize(
        ("filter_by", "expected"),
        [("patient2", ["m3"]), ("neuro", ["m2"]), ("cardio", ["m3", "m1"])],
    )
    def test_list_can_be_filtered_by_patient_or_doctor(self, alice_client, world, mappings, filter_by, expected):
        key = "patient" if filter_by.startswith("patient") else "doctor"
        res = alice_client.get(LIST, {key: world[filter_by].id})
        assert [m["id"] for m in res.json()] == [mappings[name].id for name in expected]

    def test_patient_filter_does_not_reveal_whether_an_id_exists(self, alice_client, world, mappings):
        """Another user's patient and a nonexistent one must look exactly alike."""
        foreign = alice_client.get(LIST, {"patient": world["bobs_patient"].id})
        missing = alice_client.get(LIST, {"patient": 999_999})
        assert (foreign.status_code, foreign.json()) == (200, [])
        assert (missing.status_code, missing.json()) == (200, [])

    @pytest.mark.parametrize("params", [{"patient": "abc"}, {"doctor": "xyz"}])
    def test_non_numeric_filter_values_are_a_400(self, alice_client, params):
        assert_error(alice_client.get(LIST, params), 400, "validation_error")

    def test_doctors_of_a_patient(self, alice_client, world, mappings):
        res = alice_client.get(detail(world["patient"].id))
        assert res.status_code == 200
        body = res.json()
        assert [m["doctor"]["name"] for m in body] == ["Dr. Cardio", "Dr. Neuro"]  # ordered by doctor name
        assert {m["id"] for m in body} == {mappings["m1"].id, mappings["m2"].id}
        assert all(m["patient"] == world["patient"].id for m in body)

    def test_doctors_of_a_patient_embeds_full_doctor_details(self, alice_client, world, mappings):
        doctor = alice_client.get(detail(world["patient"].id)).json()[0]["doctor"]
        assert {"id", "name", "specialization", "email", "phone", "years_of_experience"} <= set(doctor)

    def test_patient_without_doctors_gets_an_empty_list(self, alice_client, patient_factory, alice):
        lonely = patient_factory(created_by=alice)
        res = alice_client.get(detail(lonely.id))
        assert (res.status_code, res.json()) == (200, [])

    def test_doctors_of_someone_elses_patient_is_a_404(self, alice_client, world, mappings):
        assert_error(alice_client.get(detail(world["bobs_patient"].id)), 404, "not_found")

    def test_doctors_of_an_unknown_patient_is_a_404(self, alice_client):
        assert_error(alice_client.get(detail(999_999)), 404, "not_found")


class TestRemove:
    @pytest.fixture
    def mapping(self, world):
        return PatientDoctorMapping.objects.create(patient=world["patient"], doctor=world["cardio"])

    def test_removes_the_assignment_but_not_the_people(self, alice_client, world, mapping):
        assert alice_client.delete(detail(mapping.id)).status_code == 204
        assert not PatientDoctorMapping.objects.filter(pk=mapping.id).exists()
        assert Patient.objects.filter(pk=world["patient"].id).exists()
        assert Doctor.objects.filter(pk=world["cardio"].id).exists()

    def test_cannot_remove_another_users_mapping(self, alice_client, world):
        theirs = PatientDoctorMapping.objects.create(patient=world["bobs_patient"], doctor=world["cardio"])
        assert_error(alice_client.delete(detail(theirs.id)), 404, "not_found")
        assert PatientDoctorMapping.objects.filter(pk=theirs.id).exists()

    def test_unknown_mapping(self, alice_client):
        assert_error(alice_client.delete(detail(999_999)), 404, "not_found")

    def test_double_delete_is_a_404(self, alice_client, mapping):
        alice_client.delete(detail(mapping.id))
        assert_error(alice_client.delete(detail(mapping.id)), 404, "not_found")

    def test_doctor_can_be_reassigned_after_removal(self, alice_client, world, mapping):
        alice_client.delete(detail(mapping.id))
        assert assign(alice_client, world["patient"], world["cardio"]).status_code == 201


class TestCascades:
    """Deleting a patient/doctor through the public API cleans up assignments."""

    def test_deleting_a_patient_removes_their_assignments(self, alice_client, world):
        mapping = PatientDoctorMapping.objects.create(patient=world["patient"], doctor=world["cardio"])
        alice_client.delete(reverse("patient-detail", kwargs={"pk": world["patient"].id}))
        assert not PatientDoctorMapping.objects.filter(pk=mapping.id).exists()

    def test_deleting_a_doctor_removes_their_assignments_everywhere(self, alice_client, world):
        PatientDoctorMapping.objects.create(patient=world["patient"], doctor=world["cardio"])
        PatientDoctorMapping.objects.create(patient=world["bobs_patient"], doctor=world["cardio"])
        alice_client.delete(reverse("doctor-detail", kwargs={"pk": world["cardio"].id}))
        assert PatientDoctorMapping.objects.count() == 0
        assert Patient.objects.count() == 3


class TestConcurrencySafety:
    """A race that slips past serializer validation must degrade to a clean 409."""

    def test_duplicate_that_bypasses_validation_returns_409_and_leaves_no_partial_write(
        self, alice_client, world, monkeypatch
    ):
        assign(alice_client, world["patient"], world["cardio"])
        # Simulate the losing side of a race: the "already assigned?" pre-check
        # passed, so only the database constraint can stop the second insert.
        monkeypatch.setattr(MappingSerializer.Meta, "validators", [])
        res = assign(alice_client, world["patient"], world["cardio"])
        assert_error(res, 409, "conflict")
        assert PatientDoctorMapping.objects.count() == 1

    def test_without_the_race_the_friendly_pre_check_answers_with_400(self, alice_client, world):
        assign(alice_client, world["patient"], world["cardio"])
        assert assign(alice_client, world["patient"], world["cardio"]).status_code == 400

    def test_conflict_response_does_not_leak_constraint_names(self, alice_client, world, monkeypatch):
        assign(alice_client, world["patient"], world["cardio"])
        monkeypatch.setattr(MappingSerializer.Meta, "validators", [])
        body = assign(alice_client, world["patient"], world["cardio"]).content.decode()
        assert "unique_patient_doctor_mapping" not in body
        assert "mappings_patientdoctormapping" not in body

    def test_the_connection_stays_usable_after_a_409(self, alice_client, world, monkeypatch):
        assign(alice_client, world["patient"], world["cardio"])
        monkeypatch.setattr(MappingSerializer.Meta, "validators", [])
        assign(alice_client, world["patient"], world["cardio"])
        assert not connection.needs_rollback
        assert alice_client.get(LIST).status_code == 200


def test_mapping_serializer_without_a_request_context_does_not_crash():
    """get_fields() must tolerate being built without a request (e.g. schema tools)."""
    serializer = MappingSerializer()
    assert "patient" in serializer.fields
    with pytest.raises(ValidationError):
        serializer.run_validation({})

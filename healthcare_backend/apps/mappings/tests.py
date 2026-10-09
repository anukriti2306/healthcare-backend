from apps.core.testing import APITestBase
from apps.doctors.models import Doctor
from apps.patients.models import Patient

from .models import PatientDoctorMapping

URL = "/api/mappings/"


class MappingTestBase(APITestBase):
    def setUp(self):
        super().setUp()
        self.patient = Patient.objects.create(name="Alice's Patient", age=40, created_by=self.alice)
        self.patient2 = Patient.objects.create(name="Alice's Patient 2", age=50, created_by=self.alice)
        self.bobs_patient = Patient.objects.create(name="Bob's Patient", age=30, created_by=self.bob)
        self.cardio = Doctor.objects.create(name="Dr. Cardio", specialization="Cardiology", created_by=self.alice)
        self.neuro = Doctor.objects.create(name="Dr. Neuro", specialization="Neurology", created_by=self.bob)


class MappingCreateTests(MappingTestBase):
    def test_assign_doctor_to_patient(self):
        res = self.alice_client.post(URL, {"patient": self.patient.id, "doctor": self.cardio.id}, format="json")
        self.assertEqual(res.status_code, 201, res.content)
        body = res.json()
        self.assertEqual(body["patient"], self.patient.id)
        self.assertEqual(body["doctor_name"], "Dr. Cardio")
        self.assertEqual(body["doctor_specialization"], "Cardiology")

    def test_can_assign_a_doctor_created_by_another_user(self):
        res = self.alice_client.post(URL, {"patient": self.patient.id, "doctor": self.neuro.id}, format="json")
        self.assertEqual(res.status_code, 201, res.content)

    def test_duplicate_assignment_rejected(self):
        data = {"patient": self.patient.id, "doctor": self.cardio.id}
        self.alice_client.post(URL, data, format="json")
        res = self.alice_client.post(URL, data, format="json")
        error = self.assertError(res, 400, "validation_error")
        self.assertIn("already assigned", str(error["details"]))
        self.assertEqual(PatientDoctorMapping.objects.count(), 1)

    def test_same_doctor_can_serve_multiple_patients(self):
        self.alice_client.post(URL, {"patient": self.patient.id, "doctor": self.cardio.id}, format="json")
        res = self.alice_client.post(URL, {"patient": self.patient2.id, "doctor": self.cardio.id}, format="json")
        self.assertEqual(res.status_code, 201, res.content)

    def test_cannot_assign_to_someone_elses_patient(self):
        res = self.alice_client.post(URL, {"patient": self.bobs_patient.id, "doctor": self.cardio.id}, format="json")
        error = self.assertError(res, 400, "validation_error")
        self.assertEqual(error["details"]["patient"], ["Patient not found."])
        self.assertEqual(PatientDoctorMapping.objects.count(), 0)

    def test_unknown_patient_or_doctor(self):
        res = self.alice_client.post(URL, {"patient": 999999, "doctor": self.cardio.id}, format="json")
        self.assertEqual(self.assertError(res, 400)["details"]["patient"], ["Patient not found."])
        res = self.alice_client.post(URL, {"patient": self.patient.id, "doctor": 999999}, format="json")
        self.assertEqual(self.assertError(res, 400)["details"]["doctor"], ["Doctor not found."])

    def test_missing_fields(self):
        error = self.assertError(self.alice_client.post(URL, {}, format="json"), 400, "validation_error")
        self.assertEqual(set(error["details"]), {"patient", "doctor"})

    def test_non_numeric_ids(self):
        res = self.alice_client.post(URL, {"patient": "abc", "doctor": "xyz"}, format="json")
        self.assertError(res, 400, "validation_error")


class MappingReadTests(MappingTestBase):
    def setUp(self):
        super().setUp()
        self.m1 = PatientDoctorMapping.objects.create(patient=self.patient, doctor=self.cardio)
        self.m2 = PatientDoctorMapping.objects.create(patient=self.patient, doctor=self.neuro)
        self.m3 = PatientDoctorMapping.objects.create(patient=self.patient2, doctor=self.cardio)
        self.bobs_mapping = PatientDoctorMapping.objects.create(patient=self.bobs_patient, doctor=self.cardio)

    def test_list_only_shows_mappings_for_own_patients(self):
        body = self.alice_client.get(URL).json()
        self.assertIsInstance(body, list)
        self.assertEqual({m["id"] for m in body}, {self.m1.id, self.m2.id, self.m3.id})

    def test_list_filter_by_patient_and_doctor(self):
        by_patient = self.alice_client.get(URL, {"patient": self.patient2.id}).json()
        self.assertEqual([m["id"] for m in by_patient], [self.m3.id])
        by_doctor = self.alice_client.get(URL, {"doctor": self.neuro.id}).json()
        self.assertEqual([m["id"] for m in by_doctor], [self.m2.id])

    def test_doctors_of_a_patient(self):
        res = self.alice_client.get(f"{URL}{self.patient.id}/")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual([m["doctor"]["name"] for m in body], ["Dr. Cardio", "Dr. Neuro"])
        self.assertEqual({m["id"] for m in body}, {self.m1.id, self.m2.id})
        self.assertTrue(all(m["patient"] == self.patient.id for m in body))

    def test_patient_without_doctors_returns_empty_list(self):
        lonely = Patient.objects.create(name="Lonely", age=1, created_by=self.alice)
        res = self.alice_client.get(f"{URL}{lonely.id}/")
        self.assertEqual((res.status_code, res.json()), (200, []))

    def test_cannot_view_doctors_of_someone_elses_patient(self):
        self.assertError(self.alice_client.get(f"{URL}{self.bobs_patient.id}/"), 404, "not_found")

    def test_unknown_patient(self):
        self.assertError(self.alice_client.get(f"{URL}999999/"), 404, "not_found")


class MappingDeleteTests(MappingTestBase):
    def setUp(self):
        super().setUp()
        self.mapping = PatientDoctorMapping.objects.create(patient=self.patient, doctor=self.cardio)
        self.bobs_mapping = PatientDoctorMapping.objects.create(patient=self.bobs_patient, doctor=self.cardio)

    def test_delete_mapping(self):
        res = self.alice_client.delete(f"{URL}{self.mapping.id}/")
        self.assertEqual(res.status_code, 204)
        self.assertFalse(PatientDoctorMapping.objects.filter(pk=self.mapping.id).exists())
        # patient and doctor themselves are untouched
        self.assertTrue(Patient.objects.filter(pk=self.patient.id).exists())
        self.assertTrue(Doctor.objects.filter(pk=self.cardio.id).exists())

    def test_cannot_delete_someone_elses_mapping(self):
        self.assertError(self.alice_client.delete(f"{URL}{self.bobs_mapping.id}/"), 404, "not_found")
        self.assertTrue(PatientDoctorMapping.objects.filter(pk=self.bobs_mapping.id).exists())

    def test_delete_unknown_mapping(self):
        self.assertError(self.alice_client.delete(f"{URL}999999/"), 404, "not_found")

    def test_can_reassign_after_delete(self):
        self.alice_client.delete(f"{URL}{self.mapping.id}/")
        res = self.alice_client.post(URL, {"patient": self.patient.id, "doctor": self.cardio.id}, format="json")
        self.assertEqual(res.status_code, 201, res.content)

    def test_deleting_patient_removes_their_mappings(self):
        self.alice_client.delete(f"/api/patients/{self.patient.id}/")
        self.assertFalse(PatientDoctorMapping.objects.filter(pk=self.mapping.id).exists())

    def test_deleting_doctor_removes_their_mappings(self):
        self.alice_client.delete(f"/api/doctors/{self.cardio.id}/")
        self.assertEqual(PatientDoctorMapping.objects.count(), 0)


class MappingEndToEndTest(APITestBase):
    """The whole happy path through the public API only."""

    def test_full_flow(self):
        c = self.alice_client
        patient = c.post("/api/patients/", {"name": "Ravi", "age": 51, "gender": "male"}, format="json").json()
        doctor = c.post("/api/doctors/", {"name": "Dr. Meera", "specialization": "Oncology"}, format="json").json()

        mapping = c.post(URL, {"patient": patient["id"], "doctor": doctor["id"]}, format="json").json()
        self.assertEqual(c.get(URL).json()[0]["id"], mapping["id"])

        assigned = c.get(f"{URL}{patient['id']}/").json()
        self.assertEqual(assigned[0]["doctor"]["id"], doctor["id"])
        self.assertEqual(assigned[0]["id"], mapping["id"])

        self.assertEqual(c.delete(f"{URL}{mapping['id']}/").status_code, 204)
        self.assertEqual(c.get(f"{URL}{patient['id']}/").json(), [])

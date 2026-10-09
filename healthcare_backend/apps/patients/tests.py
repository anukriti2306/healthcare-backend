from apps.core.testing import APITestBase

from .models import Patient

URL = "/api/patients/"


def payload(**overrides):
    data = {
        "name": "John Doe",
        "age": 42,
        "gender": "male",
        "phone": "+91 98765 43210",
        "address": "12 MG Road, Bengaluru",
        "medical_history": "Hypertension",
    }
    data.update(overrides)
    return data


class PatientCreateTests(APITestBase):
    def test_create_patient(self):
        res = self.alice_client.post(URL, payload(), format="json")
        self.assertEqual(res.status_code, 201, res.content)
        body = res.json()
        self.assertEqual(body["name"], "John Doe")
        self.assertEqual(body["created_by"], self.alice.id)
        patient = Patient.objects.get(pk=body["id"])
        self.assertEqual(patient.created_by, self.alice)

    def test_only_name_and_age_are_required(self):
        res = self.alice_client.post(URL, {"name": "Jane", "age": 30}, format="json")
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.json()["gender"], "")

    def test_created_by_cannot_be_spoofed(self):
        res = self.alice_client.post(URL, payload(created_by=self.bob.id), format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["created_by"], self.alice.id)

    def test_gender_aliases_are_normalised(self):
        for given, expected in [("M", "male"), ("Female", "female"), (" o ", "other")]:
            with self.subTest(gender=given):
                res = self.alice_client.post(URL, payload(gender=given), format="json")
                self.assertEqual(res.status_code, 201, res.content)
                self.assertEqual(res.json()["gender"], expected)

    def test_validation_errors(self):
        cases = {
            "name": payload(name=""),
            "age": payload(age=-1),
            "age_too_high": payload(age=200),
            "age_text": payload(age="abc"),
            "gender": payload(gender="robot"),
            "phone": payload(phone="call me"),
        }
        for label, data in cases.items():
            with self.subTest(case=label):
                res = self.alice_client.post(URL, data, format="json")
                self.assertError(res, 400, "validation_error")
        self.assertEqual(Patient.objects.count(), 0)

    def test_missing_required_fields(self):
        error = self.assertError(self.alice_client.post(URL, {}, format="json"), 400)
        self.assertEqual(set(error["details"]), {"name", "age"})


class PatientReadTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.p1 = Patient.objects.create(name="Alpha", age=20, gender="male", created_by=self.alice)
        self.p2 = Patient.objects.create(name="Beta", age=60, gender="female", created_by=self.alice)
        self.bobs = Patient.objects.create(name="Bobs Patient", age=33, created_by=self.bob)

    def test_list_returns_plain_array_of_own_patients_only(self):
        res = self.alice_client.get(URL)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIsInstance(body, list)
        self.assertEqual({p["id"] for p in body}, {self.p1.id, self.p2.id})

    def test_list_is_newest_first(self):
        ids = [p["id"] for p in self.alice_client.get(URL).json()]
        self.assertEqual(ids, [self.p2.id, self.p1.id])

    def test_retrieve_own_patient(self):
        res = self.alice_client.get(f"{URL}{self.p1.id}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["name"], "Alpha")

    def test_cannot_retrieve_someone_elses_patient(self):
        self.assertError(self.alice_client.get(f"{URL}{self.bobs.id}/"), 404, "not_found")

    def test_nonexistent_patient_404(self):
        self.assertError(self.alice_client.get(f"{URL}999999/"), 404, "not_found")

    def test_non_numeric_id_404(self):
        self.assertEqual(self.alice_client.get(f"{URL}abc/").status_code, 404)

    def test_filter_search_ordering(self):
        self.assertEqual([p["name"] for p in self.alice_client.get(URL, {"gender": "FEMALE"}).json()], ["Beta"])
        self.assertEqual([p["name"] for p in self.alice_client.get(URL, {"min_age": 50}).json()], ["Beta"])
        self.assertEqual([p["name"] for p in self.alice_client.get(URL, {"search": "alp"}).json()], ["Alpha"])
        self.assertEqual(
            [p["name"] for p in self.alice_client.get(URL, {"ordering": "-age"}).json()],
            ["Beta", "Alpha"],
        )

    def test_invalid_filter_value_returns_400(self):
        self.assertError(self.alice_client.get(URL, {"min_age": "abc"}), 400, "validation_error")

    def test_opt_in_pagination(self):
        res = self.alice_client.get(URL, {"limit": 1})
        body = res.json()
        self.assertEqual(body["count"], 2)
        self.assertEqual(len(body["results"]), 1)
        self.assertIsNotNone(body["next"])


class PatientUpdateDeleteTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.patient = Patient.objects.create(
            name="Alpha", age=20, gender="male", phone="+911234567890", created_by=self.alice
        )
        self.bobs = Patient.objects.create(name="Bobs Patient", age=33, created_by=self.bob)

    def test_put_updates_patient(self):
        res = self.alice_client.put(f"{URL}{self.patient.id}/", payload(name="Alpha Prime", age=21), format="json")
        self.assertEqual(res.status_code, 200, res.content)
        self.patient.refresh_from_db()
        self.assertEqual((self.patient.name, self.patient.age), ("Alpha Prime", 21))

    def test_put_requires_required_fields(self):
        res = self.alice_client.put(f"{URL}{self.patient.id}/", {"name": "Only name"}, format="json")
        self.assertError(res, 400, "validation_error")

    def test_patch_partial_update_keeps_other_fields(self):
        res = self.alice_client.patch(f"{URL}{self.patient.id}/", {"age": 25}, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        self.patient.refresh_from_db()
        self.assertEqual((self.patient.name, self.patient.age, self.patient.phone), ("Alpha", 25, "+911234567890"))

    def test_update_cannot_change_owner(self):
        self.alice_client.patch(f"{URL}{self.patient.id}/", {"created_by": self.bob.id}, format="json")
        self.patient.refresh_from_db()
        self.assertEqual(self.patient.created_by, self.alice)

    def test_cannot_update_someone_elses_patient(self):
        res = self.alice_client.put(f"{URL}{self.bobs.id}/", payload(), format="json")
        self.assertError(res, 404, "not_found")
        self.bobs.refresh_from_db()
        self.assertEqual(self.bobs.name, "Bobs Patient")

    def test_delete_patient(self):
        res = self.alice_client.delete(f"{URL}{self.patient.id}/")
        self.assertEqual(res.status_code, 204)
        self.assertFalse(Patient.objects.filter(pk=self.patient.id).exists())

    def test_cannot_delete_someone_elses_patient(self):
        res = self.alice_client.delete(f"{URL}{self.bobs.id}/")
        self.assertError(res, 404, "not_found")
        self.assertTrue(Patient.objects.filter(pk=self.bobs.id).exists())

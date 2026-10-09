from apps.core.testing import APITestBase

from .models import Doctor

URL = "/api/doctors/"


def payload(**overrides):
    data = {
        "name": "Dr. Asha Rao",
        "specialization": "Cardiology",
        "email": "asha.rao@hospital.com",
        "phone": "+91 80 2345 6789",
        "years_of_experience": 12,
    }
    data.update(overrides)
    return data


class DoctorCreateTests(APITestBase):
    def test_create_doctor(self):
        res = self.alice_client.post(URL, payload(), format="json")
        self.assertEqual(res.status_code, 201, res.content)
        body = res.json()
        self.assertEqual(body["specialization"], "Cardiology")
        self.assertEqual(body["created_by"], self.alice.id)

    def test_only_name_and_specialization_required(self):
        res = self.alice_client.post(URL, {"name": "Dr. X", "specialization": "ENT"}, format="json")
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.json()["email"], "")

    def test_two_doctors_without_email_are_allowed(self):
        for name in ("Dr. A", "Dr. B"):
            res = self.alice_client.post(URL, {"name": name, "specialization": "ENT"}, format="json")
            self.assertEqual(res.status_code, 201, res.content)

    def test_email_stored_lowercase_and_unique_case_insensitively(self):
        first = self.alice_client.post(URL, payload(email="Doc@Hospital.com"), format="json")
        self.assertEqual(first.json()["email"], "doc@hospital.com")
        dup = self.bob_client.post(URL, payload(name="Other", email="DOC@hospital.COM"), format="json")
        error = self.assertError(dup, 400, "validation_error")
        self.assertIn("email", error["details"])

    def test_validation_errors(self):
        cases = {
            "name": payload(name=""),
            "specialization": payload(specialization=""),
            "email": payload(email="nope"),
            "experience_negative": payload(years_of_experience=-2),
            "experience_too_high": payload(years_of_experience=99),
            "phone": payload(phone="abc"),
        }
        for label, data in cases.items():
            with self.subTest(case=label):
                self.assertError(self.alice_client.post(URL, data, format="json"), 400, "validation_error")
        self.assertEqual(Doctor.objects.count(), 0)


class DoctorReadTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.d1 = Doctor.objects.create(name="Dr. Zed", specialization="Cardiology", years_of_experience=20, created_by=self.alice)
        self.d2 = Doctor.objects.create(name="Dr. Amy", specialization="Neurology", years_of_experience=5, created_by=self.bob)

    def test_list_shows_all_doctors_to_any_user(self):
        for client in (self.alice_client, self.bob_client):
            body = client.get(URL).json()
            self.assertIsInstance(body, list)
            self.assertEqual({d["id"] for d in body}, {self.d1.id, self.d2.id})

    def test_list_ordered_by_name(self):
        self.assertEqual([d["name"] for d in self.alice_client.get(URL).json()], ["Dr. Amy", "Dr. Zed"])

    def test_retrieve_any_doctor(self):
        res = self.alice_client.get(f"{URL}{self.d2.id}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["name"], "Dr. Amy")

    def test_not_found(self):
        self.assertError(self.alice_client.get(f"{URL}999999/"), 404, "not_found")

    def test_filter_and_search(self):
        names = lambda params: [d["name"] for d in self.alice_client.get(URL, params).json()]  # noqa: E731
        self.assertEqual(names({"specialization": "cardiology"}), ["Dr. Zed"])
        self.assertEqual(names({"min_experience": 10}), ["Dr. Zed"])
        self.assertEqual(names({"search": "neuro"}), ["Dr. Amy"])
        self.assertEqual(names({"ordering": "-years_of_experience"}), ["Dr. Zed", "Dr. Amy"])


class DoctorUpdateDeleteTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.doctor = Doctor.objects.create(
            name="Dr. Zed", specialization="Cardiology", email="zed@hospital.com", created_by=self.alice
        )

    def test_creator_can_put(self):
        res = self.alice_client.put(f"{URL}{self.doctor.id}/", payload(name="Dr. Zed II", email="zed@hospital.com"), format="json")
        self.assertEqual(res.status_code, 200, res.content)
        self.doctor.refresh_from_db()
        self.assertEqual(self.doctor.name, "Dr. Zed II")

    def test_creator_can_patch_and_keep_own_email(self):
        res = self.alice_client.patch(f"{URL}{self.doctor.id}/", {"email": "ZED@hospital.com"}, format="json")
        self.assertEqual(res.status_code, 200, res.content)

    def test_update_email_to_existing_one_rejected(self):
        Doctor.objects.create(name="Dr. Other", specialization="ENT", email="taken@hospital.com", created_by=self.bob)
        res = self.alice_client.patch(f"{URL}{self.doctor.id}/", {"email": "taken@hospital.com"}, format="json")
        self.assertError(res, 400, "validation_error")

    def test_other_user_cannot_update(self):
        res = self.bob_client.put(f"{URL}{self.doctor.id}/", payload(), format="json")
        self.assertError(res, 403, "permission_denied")
        res = self.bob_client.patch(f"{URL}{self.doctor.id}/", {"name": "Hacked"}, format="json")
        self.assertError(res, 403, "permission_denied")
        self.doctor.refresh_from_db()
        self.assertEqual(self.doctor.name, "Dr. Zed")

    def test_creator_can_delete(self):
        self.assertEqual(self.alice_client.delete(f"{URL}{self.doctor.id}/").status_code, 204)
        self.assertFalse(Doctor.objects.filter(pk=self.doctor.id).exists())

    def test_other_user_cannot_delete(self):
        self.assertError(self.bob_client.delete(f"{URL}{self.doctor.id}/"), 403, "permission_denied")
        self.assertTrue(Doctor.objects.filter(pk=self.doctor.id).exists())

    def test_doctor_survives_deletion_of_creator_account(self):
        self.alice.delete()
        self.doctor.refresh_from_db()
        self.assertIsNone(self.doctor.created_by)

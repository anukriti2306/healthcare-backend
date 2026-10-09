"""Doctors API: shared directory with creator-only write access."""
import pytest
from django.urls import reverse

from apps.doctors.models import Doctor
from tests.helpers import assert_error, doctor_payload, names

LIST = reverse("doctor-list")


def detail(pk):
    return reverse("doctor-detail", kwargs={"pk": pk})


class TestCreate:
    def test_creates_and_records_the_creator(self, alice_client, alice):
        res = alice_client.post(LIST, doctor_payload(), format="json")
        assert res.status_code == 201, res.content
        body = res.json()
        assert body["specialization"] == "Cardiology"
        assert body["created_by"] == alice.id

    def test_only_name_and_specialization_are_required(self, alice_client):
        res = alice_client.post(LIST, {"name": "Dr. X", "specialization": "ENT"}, format="json")
        assert res.status_code == 201, res.content
        body = res.json()
        assert (body["email"], body["phone"], body["years_of_experience"]) == ("", "", 0)

    def test_created_by_cannot_be_spoofed(self, alice_client, alice, bob):
        res = alice_client.post(LIST, doctor_payload(created_by=bob.id), format="json")
        assert res.json()["created_by"] == alice.id

    @pytest.mark.parametrize("years", [0, 1, 70])
    def test_experience_boundaries_accepted(self, alice_client, years):
        res = alice_client.post(LIST, doctor_payload(years_of_experience=years, email=""), format="json")
        assert res.status_code == 201, res.content

    @pytest.mark.parametrize("years", [-1, 71, 999, "many", 3.5, None])
    def test_invalid_experience_rejected(self, alice_client, years):
        error = assert_error(alice_client.post(LIST, doctor_payload(years_of_experience=years), format="json"), 400)
        assert "years_of_experience" in error["details"]

    @pytest.mark.parametrize(
        ("overrides", "bad_field"),
        [
            pytest.param({"name": ""}, "name", id="blank-name"),
            pytest.param({"specialization": ""}, "specialization", id="blank-specialization"),
            pytest.param({"email": "not-an-email"}, "email", id="bad-email"),
            pytest.param({"phone": "abc"}, "phone", id="bad-phone"),
            pytest.param({"name": "n" * 151}, "name", id="name-too-long"),
            pytest.param({"specialization": "s" * 101}, "specialization", id="specialization-too-long"),
        ],
    )
    def test_validation_errors(self, alice_client, overrides, bad_field):
        error = assert_error(alice_client.post(LIST, doctor_payload(**overrides), format="json"), 400)
        assert bad_field in error["details"]
        assert Doctor.objects.count() == 0

    def test_email_is_stored_lowercase(self, alice_client):
        res = alice_client.post(LIST, doctor_payload(email="  Doc@Hospital.COM "), format="json")
        assert res.json()["email"] == "doc@hospital.com"

    def test_email_is_unique_across_all_users_case_insensitively(self, alice_client, bob_client):
        alice_client.post(LIST, doctor_payload(email="Doc@Hospital.com"), format="json")
        res = bob_client.post(LIST, doctor_payload(name="Other", email="DOC@hospital.COM"), format="json")
        error = assert_error(res, 400, "validation_error")
        assert "email" in error["details"]
        assert Doctor.objects.count() == 1

    def test_doctors_without_email_do_not_collide(self, alice_client):
        for name in ("Dr. A", "Dr. B", "Dr. C"):
            res = alice_client.post(LIST, {"name": name, "specialization": "ENT"}, format="json")
            assert res.status_code == 201, res.content


class TestRead:
    @pytest.fixture
    def data(self, alice, bob, doctor_factory):
        return {
            "zed": doctor_factory(name="Dr. Zed", specialization="Cardiology", years_of_experience=20,
                                  email="zed@hospital.com", created_by=alice),
            "amy": doctor_factory(name="Dr. Amy", specialization="Neurology", years_of_experience=5,
                                  email="amy@clinic.org", created_by=bob),
            "mia": doctor_factory(name="Dr. Mia", specialization="Cardiology", years_of_experience=12,
                                  created_by=None),
        }

    def test_every_user_sees_every_doctor(self, alice_client, bob_client, data):
        for client in (alice_client, bob_client):
            body = client.get(LIST).json()
            assert isinstance(body, list)
            assert {d["name"] for d in body} == {"Dr. Zed", "Dr. Amy", "Dr. Mia"}

    def test_default_ordering_is_by_name(self, alice_client, data):
        assert names(alice_client.get(LIST)) == ["Dr. Amy", "Dr. Mia", "Dr. Zed"]

    def test_any_user_can_retrieve_any_doctor(self, alice_client, data):
        res = alice_client.get(detail(data["amy"].id))
        assert res.status_code == 200 and res.json()["name"] == "Dr. Amy"

    def test_orphaned_doctor_is_still_readable(self, alice_client, data):
        res = alice_client.get(detail(data["mia"].id))
        assert res.status_code == 200 and res.json()["created_by"] is None

    def test_unknown_doctor(self, alice_client):
        assert_error(alice_client.get(detail(999_999)), 404, "not_found")

    @pytest.mark.parametrize(
        ("params", "expected"),
        [
            pytest.param({"specialization": "cardiology"}, ["Dr. Mia", "Dr. Zed"], id="specialization-ci"),
            pytest.param({"specialization": "Cardio"}, [], id="specialization-is-exact"),
            pytest.param({"min_experience": 10}, ["Dr. Mia", "Dr. Zed"], id="min-experience"),
            pytest.param({"min_experience": 12}, ["Dr. Mia", "Dr. Zed"], id="min-experience-inclusive"),
            pytest.param({"specialization": "cardiology", "min_experience": 15}, ["Dr. Zed"], id="combined"),
            pytest.param({"search": "neuro"}, ["Dr. Amy"], id="search-specialization"),
            pytest.param({"search": "clinic.org"}, ["Dr. Amy"], id="search-email"),
            pytest.param({"search": "zed"}, ["Dr. Zed"], id="search-name"),
            pytest.param({"ordering": "-years_of_experience"}, ["Dr. Zed", "Dr. Mia", "Dr. Amy"], id="order-exp-desc"),
            pytest.param({"ordering": "specialization,name", "search": "dr"}, ["Dr. Mia", "Dr. Zed", "Dr. Amy"],
                         id="multi-key-ordering-with-search"),
        ],
    )
    def test_filter_search_ordering(self, alice_client, data, params, expected):
        res = alice_client.get(LIST, params)
        assert res.status_code == 200, res.content
        assert names(res) == expected

    def test_non_numeric_min_experience_is_a_400(self, alice_client):
        assert_error(alice_client.get(LIST, {"min_experience": "lots"}), 400, "validation_error")


class TestWritePermissions:
    @pytest.fixture
    def doctor(self, alice, doctor_factory):
        return doctor_factory(name="Dr. Zed", specialization="Cardiology", email="zed@hospital.com", created_by=alice)

    def test_creator_can_put(self, alice_client, doctor):
        res = alice_client.put(detail(doctor.id), doctor_payload(name="Dr. Zed II", email="zed@hospital.com"),
                               format="json")
        assert res.status_code == 200, res.content
        doctor.refresh_from_db()
        assert doctor.name == "Dr. Zed II"

    def test_creator_can_patch_keeping_their_own_email(self, alice_client, doctor):
        res = alice_client.patch(detail(doctor.id), {"email": "ZED@hospital.com"}, format="json")
        assert res.status_code == 200, res.content

    def test_creator_can_delete(self, alice_client, doctor):
        assert alice_client.delete(detail(doctor.id)).status_code == 204
        assert not Doctor.objects.filter(pk=doctor.id).exists()

    def test_updating_email_to_another_doctors_email_is_rejected(self, alice_client, doctor, doctor_factory):
        doctor_factory(email="taken@hospital.com")
        res = alice_client.patch(detail(doctor.id), {"email": "Taken@Hospital.com"}, format="json")
        assert_error(res, 400, "validation_error")

    @pytest.mark.parametrize(
        ("method", "body"),
        [
            pytest.param("put", doctor_payload(), id="PUT"),
            pytest.param("patch", {"name": "Hacked"}, id="PATCH"),
            pytest.param("delete", None, id="DELETE"),
        ],
    )
    def test_other_users_get_403_and_the_record_is_untouched(self, bob_client, doctor, method, body):
        res = getattr(bob_client, method)(detail(doctor.id), body, format="json")
        assert_error(res, 403, "permission_denied")
        doctor.refresh_from_db()
        assert doctor.name == "Dr. Zed"

    def test_writing_to_a_nonexistent_doctor_is_404_not_403(self, bob_client):
        assert_error(bob_client.patch(detail(999_999), {"name": "x"}, format="json"), 404, "not_found")

    def test_orphaned_doctor_is_read_only_for_everyone(self, alice_client, doctor_factory):
        orphan = doctor_factory(created_by=None)
        assert_error(alice_client.patch(detail(orphan.id), {"name": "x"}, format="json"), 403, "permission_denied")
        assert_error(alice_client.delete(detail(orphan.id)), 403, "permission_denied")

    def test_account_deletion_keeps_the_doctor_in_the_directory(self, alice_client, bob_client, alice, doctor):
        alice.delete()
        res = bob_client.get(detail(doctor.id))
        assert res.status_code == 200 and res.json()["created_by"] is None

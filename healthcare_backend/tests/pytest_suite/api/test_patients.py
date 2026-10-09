"""Patients API: CRUD, validation, ownership isolation, filtering, pagination."""
import pytest
from django.urls import reverse

from apps.patients.models import Patient
from helpers import assert_error, names, patient_payload

LIST = reverse("patient-list")


def detail(pk):
    return reverse("patient-detail", kwargs={"pk": pk})


class TestCreate:
    def test_creates_and_assigns_the_authenticated_user_as_owner(self, alice_client, alice):
        res = alice_client.post(LIST, patient_payload(), format="json")
        assert res.status_code == 201, res.content
        body = res.json()
        assert body["name"] == "John Doe"
        assert body["created_by"] == alice.id
        assert Patient.objects.get(pk=body["id"]).created_by == alice

    def test_only_name_and_age_are_required(self, alice_client):
        res = alice_client.post(LIST, {"name": "Jane", "age": 30}, format="json")
        assert res.status_code == 201, res.content
        assert res.json()["gender"] == ""
        assert res.json()["phone"] == ""

    def test_server_controlled_fields_cannot_be_set_by_the_client(self, alice_client, alice, bob):
        res = alice_client.post(
            LIST,
            patient_payload(id=999_999, created_by=bob.id, created_at="2000-01-01T00:00:00Z"),
            format="json",
        )
        assert res.status_code == 201
        body = res.json()
        assert body["id"] != 999_999
        assert body["created_by"] == alice.id
        assert not body["created_at"].startswith("2000")

    def test_unicode_data_round_trips(self, alice_client):
        data = patient_payload(name="रवि कुमार", address="Café Straße, 東京", medical_history="ऊँचा रक्तचाप")
        created = alice_client.post(LIST, data, format="json").json()
        fetched = alice_client.get(detail(created["id"])).json()
        assert (fetched["name"], fetched["address"], fetched["medical_history"]) == (
            data["name"], data["address"], data["medical_history"])

    def test_surrounding_whitespace_in_name_is_trimmed(self, alice_client):
        res = alice_client.post(LIST, patient_payload(name="  Padded  "), format="json")
        assert res.json()["name"] == "Padded"

    @pytest.mark.parametrize("age", [0, 1, 130])
    def test_age_boundaries_accepted(self, alice_client, age):
        assert alice_client.post(LIST, patient_payload(age=age), format="json").status_code == 201

    @pytest.mark.parametrize("age", [-1, 131, 10_000, "abc", 42.5, None, True, []])
    def test_invalid_age_rejected(self, alice_client, age):
        error = assert_error(alice_client.post(LIST, patient_payload(age=age), format="json"), 400)
        assert "age" in error["details"]

    @pytest.mark.parametrize(("length", "status"), [(150, 201), (151, 400)])
    def test_name_length_boundary(self, alice_client, length, status):
        assert alice_client.post(LIST, patient_payload(name="n" * length), format="json").status_code == status

    @pytest.mark.parametrize("name", ["", "   ", None])
    def test_blank_name_rejected(self, alice_client, name):
        error = assert_error(alice_client.post(LIST, patient_payload(name=name), format="json"), 400)
        assert "name" in error["details"]

    @pytest.mark.parametrize(
        ("given", "stored"),
        [("male", "male"), ("M", "male"), ("FEMALE", "female"), (" f ", "female"), ("o", "other"), ("", "")],
    )
    def test_gender_is_normalised(self, alice_client, given, stored):
        res = alice_client.post(LIST, patient_payload(gender=given), format="json")
        assert res.status_code == 201, res.content
        assert res.json()["gender"] == stored

    @pytest.mark.parametrize("gender", ["robot", "x", "malee", 123, None])
    def test_invalid_gender_rejected(self, alice_client, gender):
        error = assert_error(alice_client.post(LIST, patient_payload(gender=gender), format="json"), 400)
        assert "gender" in error["details"]

    @pytest.mark.parametrize("phone", ["call me", "123", "+", "12345\n67890", "+" + "1" * 20])
    def test_invalid_phone_rejected(self, alice_client, phone):
        error = assert_error(alice_client.post(LIST, patient_payload(phone=phone), format="json"), 400)
        assert "phone" in error["details"]

    def test_missing_required_fields_are_all_reported_together(self, alice_client):
        error = assert_error(alice_client.post(LIST, {}, format="json"), 400, "validation_error")
        assert set(error["details"]) == {"name", "age"}

    def test_nothing_is_persisted_when_validation_fails(self, alice_client):
        alice_client.post(LIST, patient_payload(age=-5), format="json")
        assert Patient.objects.count() == 0

    def test_body_must_be_a_json_object(self, alice_client):
        assert_error(alice_client.post(LIST, [1, 2, 3], format="json"), 400, "validation_error")

    def test_malformed_json(self, alice_client):
        res = alice_client.post(LIST, "{not json", content_type="application/json")
        assert_error(res, 400, "parse_error")

    def test_unsupported_content_type(self, alice_client):
        res = alice_client.post(LIST, "name=x", content_type="text/plain")
        assert_error(res, 415, "unsupported_media_type")


class TestRetrieveAndList:
    @pytest.fixture
    def data(self, alice, bob, patient_factory):
        return {
            "alpha": patient_factory(name="Alpha", age=20, gender="male", phone="+911111111111", created_by=alice),
            "beta": patient_factory(name="Beta", age=60, gender="female", phone="+922222222222", created_by=alice),
            "gamma": patient_factory(name="Gamma", age=40, gender="other", created_by=alice),
            "bobs": patient_factory(name="Bobs Patient", age=33, created_by=bob),
        }

    def test_list_is_a_plain_array_containing_only_own_patients(self, alice_client, data):
        res = alice_client.get(LIST)
        assert res.status_code == 200
        body = res.json()
        assert isinstance(body, list)
        assert {p["name"] for p in body} == {"Alpha", "Beta", "Gamma"}

    def test_new_user_sees_an_empty_list(self, user_factory, client_for):
        assert client_for(user_factory()).get(LIST).json() == []

    def test_list_is_newest_first(self, alice_client, data):
        assert names(alice_client.get(LIST)) == ["Gamma", "Beta", "Alpha"]

    def test_retrieve_own_patient(self, alice_client, data):
        res = alice_client.get(detail(data["alpha"].id))
        assert res.status_code == 200
        assert res.json()["name"] == "Alpha"

    def test_response_exposes_the_documented_fields_only(self, alice_client, data):
        keys = set(alice_client.get(detail(data["alpha"].id)).json())
        assert keys == {"id", "name", "age", "gender", "phone", "address", "medical_history",
                        "created_by", "created_at", "updated_at"}

    def test_someone_elses_patient_looks_nonexistent(self, alice_client, data):
        assert_error(alice_client.get(detail(data["bobs"].id)), 404, "not_found")

    def test_unknown_id(self, alice_client):
        assert_error(alice_client.get(detail(999_999)), 404, "not_found")

    def test_non_numeric_id(self, alice_client):
        assert_error(alice_client.get("/api/patients/abc/"), 404, "not_found")

    @pytest.mark.parametrize(
        ("params", "expected"),
        [
            pytest.param({"gender": "female"}, ["Beta"], id="gender"),
            pytest.param({"gender": "FEMALE"}, ["Beta"], id="gender-case-insensitive"),
            pytest.param({"min_age": 40}, ["Gamma", "Beta"], id="min-age-inclusive"),
            pytest.param({"max_age": 40}, ["Gamma", "Alpha"], id="max-age-inclusive"),
            pytest.param({"min_age": 30, "max_age": 50}, ["Gamma"], id="age-range"),
            pytest.param({"min_age": 61}, [], id="no-match"),
            pytest.param({"search": "alp"}, ["Alpha"], id="search-name-partial"),
            pytest.param({"search": "ALPHA"}, ["Alpha"], id="search-case-insensitive"),
            pytest.param({"search": "2222222"}, ["Beta"], id="search-phone"),
            pytest.param({"gender": "male", "min_age": 50}, [], id="filters-are-anded"),
            pytest.param({"ordering": "-age"}, ["Beta", "Gamma", "Alpha"], id="order-age-desc"),
            pytest.param({"ordering": "name"}, ["Alpha", "Beta", "Gamma"], id="order-name-asc"),
            pytest.param({"unknown_filter": "x"}, ["Gamma", "Beta", "Alpha"], id="unknown-param-ignored"),
        ],
    )
    def test_filter_search_and_ordering(self, alice_client, data, params, expected):
        res = alice_client.get(LIST, params)
        assert res.status_code == 200, res.content
        assert names(res) == expected

    def test_filters_never_widen_access_to_other_users_data(self, alice_client, data):
        assert alice_client.get(LIST, {"search": "Bobs"}).json() == []
        assert alice_client.get(LIST, {"min_age": 33, "max_age": 33}).json() == []

    @pytest.mark.parametrize("params", [{"min_age": "abc"}, {"max_age": "x"}])
    def test_invalid_filter_value_is_a_400(self, alice_client, params):
        assert_error(alice_client.get(LIST, params), 400, "validation_error")

    @pytest.mark.parametrize(
        "evil",
        ["' OR '1'='1", "'; DROP TABLE patients_patient; --", "%", "\\", "<script>alert(1)</script>"],
    )
    def test_hostile_search_strings_are_handled_safely(self, alice_client, data, evil):
        res = alice_client.get(LIST, {"search": evil})
        assert res.status_code == 200
        assert res.json() == []
        assert Patient.objects.count() == 4

    def test_null_byte_in_search_is_a_clean_400_not_a_500(self, alice_client, data):
        assert_error(alice_client.get(LIST, {"search": "\x00"}), 400, "validation_error")

    @pytest.mark.parametrize("field", ["password", "created_by__password", "id; DROP TABLE x", "created_by"])
    def test_ordering_by_a_non_whitelisted_field_is_ignored(self, alice_client, data, field):
        res = alice_client.get(LIST, {"ordering": field})
        assert res.status_code == 200
        assert names(res) == ["Gamma", "Beta", "Alpha"]  # default ordering unchanged


class TestPagination:
    @pytest.fixture
    def many(self, alice, patient_factory):
        # created oldest -> newest as "P001".. so newest-first = P105 first
        return [patient_factory(name=f"P{i:03d}", created_by=alice) for i in range(1, 106)]

    def test_off_by_default(self, alice_client, many):
        body = alice_client.get(LIST).json()
        assert isinstance(body, list) and len(body) == 105

    def test_limit_switches_to_the_envelope(self, alice_client, many):
        body = alice_client.get(LIST, {"limit": 10}).json()
        assert set(body) == {"count", "next", "previous", "results"}
        assert body["count"] == 105
        assert len(body["results"]) == 10
        assert body["previous"] is None
        assert "offset=10" in body["next"]

    def test_walking_pages_covers_every_record_exactly_once(self, alice_client, many):
        seen, url = [], f"{LIST}?limit=40"
        while url:
            body = alice_client.get(url).json()
            seen += [p["name"] for p in body["results"]]
            url = body["next"]
        assert len(seen) == 105 and len(set(seen)) == 105

    def test_last_page_has_no_next_and_has_previous(self, alice_client, many):
        body = alice_client.get(LIST, {"limit": 100, "offset": 100}).json()
        assert len(body["results"]) == 5
        assert body["next"] is None
        assert body["previous"] is not None

    def test_limit_is_capped_at_100(self, alice_client, many):
        body = alice_client.get(LIST, {"limit": 5000}).json()
        assert len(body["results"]) == 100

    def test_offset_beyond_the_end_returns_an_empty_page(self, alice_client, many):
        body = alice_client.get(LIST, {"limit": 10, "offset": 500}).json()
        assert body["results"] == [] and body["count"] == 105

    def test_pagination_composes_with_filters(self, alice_client, many):
        body = alice_client.get(LIST, {"limit": 5, "search": "P10"}).json()
        assert body["count"] == 6  # P100..P105
        assert all(p["name"].startswith("P10") for p in body["results"])


class TestUpdate:
    @pytest.fixture
    def patient(self, alice, patient_factory):
        return patient_factory(name="Alpha", age=20, gender="male", phone="+911234567890", created_by=alice)

    def test_put_replaces_the_record(self, alice_client, patient):
        res = alice_client.put(detail(patient.id), patient_payload(name="Alpha Prime", age=21), format="json")
        assert res.status_code == 200, res.content
        patient.refresh_from_db()
        assert (patient.name, patient.age) == ("Alpha Prime", 21)

    def test_put_without_required_fields_is_rejected(self, alice_client, patient):
        error = assert_error(alice_client.put(detail(patient.id), {"name": "Only"}, format="json"), 400)
        assert "age" in error["details"]

    def test_patch_changes_only_the_given_fields(self, alice_client, patient):
        res = alice_client.patch(detail(patient.id), {"age": 25}, format="json")
        assert res.status_code == 200
        patient.refresh_from_db()
        assert (patient.name, patient.age, patient.phone, patient.gender) == ("Alpha", 25, "+911234567890", "male")

    def test_empty_patch_is_a_harmless_no_op(self, alice_client, patient):
        assert alice_client.patch(detail(patient.id), {}, format="json").status_code == 200

    def test_patch_validates_just_like_post(self, alice_client, patient):
        assert_error(alice_client.patch(detail(patient.id), {"age": 500}, format="json"), 400, "validation_error")
        patient.refresh_from_db()
        assert patient.age == 20

    def test_updating_bumps_updated_at_but_not_created_at(self, alice_client, patient):
        created, before = patient.created_at, patient.updated_at
        alice_client.patch(detail(patient.id), {"age": 22}, format="json")
        patient.refresh_from_db()
        assert patient.created_at == created
        assert patient.updated_at > before

    def test_ownership_cannot_be_transferred(self, alice_client, alice, bob, patient):
        alice_client.patch(detail(patient.id), {"created_by": bob.id}, format="json")
        patient.refresh_from_db()
        assert patient.created_by == alice


class TestDelete:
    def test_deletes_the_patient(self, alice_client, alice, patient_factory):
        patient = patient_factory(created_by=alice)
        assert alice_client.delete(detail(patient.id)).status_code == 204
        assert not Patient.objects.filter(pk=patient.id).exists()

    def test_second_delete_is_a_404(self, alice_client, alice, patient_factory):
        patient = patient_factory(created_by=alice)
        alice_client.delete(detail(patient.id))
        assert_error(alice_client.delete(detail(patient.id)), 404, "not_found")

    def test_delete_removes_only_the_targeted_patient(self, alice_client, alice, patient_factory):
        keep, drop = patient_factory(created_by=alice), patient_factory(created_by=alice)
        alice_client.delete(detail(drop.id))
        assert list(Patient.objects.values_list("id", flat=True)) == [keep.id]


def test_collection_url_does_not_accept_put_or_delete(alice_client):
    assert_error(alice_client.put(LIST, patient_payload(), format="json"), 405, "method_not_allowed")
    assert_error(alice_client.delete(LIST), 405, "method_not_allowed")

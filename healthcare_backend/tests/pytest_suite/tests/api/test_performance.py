"""
Query-count regression tests.

Each test measures the number of SQL queries for a small and a large dataset.
They must be equal: response cost may not grow with the number of rows (N+1).
"""
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse


def count_queries(client, url):
    with CaptureQueriesContext(connection) as ctx:
        res = client.get(url)
    assert res.status_code == 200, res.content
    return len(ctx)


def test_patient_list_is_constant_in_queries(alice_client, alice, patient_factory):
    url = reverse("patient-list")
    for _ in range(2):
        patient_factory(created_by=alice)
    small = count_queries(alice_client, url)
    for _ in range(30):
        patient_factory(created_by=alice)
    assert count_queries(alice_client, url) == small


def test_doctor_list_is_constant_in_queries(alice_client, doctor_factory):
    url = reverse("doctor-list")
    for _ in range(2):
        doctor_factory()
    small = count_queries(alice_client, url)
    for _ in range(30):
        doctor_factory()
    assert count_queries(alice_client, url) == small


def test_mapping_list_is_constant_in_queries(alice_client, alice, patient_factory, doctor_factory, mapping_factory):
    url = reverse("mapping-list")
    patient = patient_factory(created_by=alice)
    for _ in range(2):
        mapping_factory(patient=patient, doctor=doctor_factory())
    small = count_queries(alice_client, url)
    for _ in range(30):
        mapping_factory(patient=patient_factory(created_by=alice), doctor=doctor_factory())
    assert count_queries(alice_client, url) == small


def test_doctors_of_a_patient_is_constant_in_queries(
    alice_client, alice, patient_factory, doctor_factory, mapping_factory
):
    patient = patient_factory(created_by=alice)
    url = reverse("mapping-detail", kwargs={"pk": patient.id})
    for _ in range(2):
        mapping_factory(patient=patient, doctor=doctor_factory())
    small = count_queries(alice_client, url)
    for _ in range(30):
        mapping_factory(patient=patient, doctor=doctor_factory())
    assert count_queries(alice_client, url) == small


@pytest.mark.parametrize("name", ["patient-list", "doctor-list", "mapping-list"])
def test_list_endpoints_use_a_small_bounded_number_of_queries(alice_client, name):
    # auth lookup + savepoint bookkeeping + the data query; generous headroom.
    assert count_queries(alice_client, reverse(name)) <= 6

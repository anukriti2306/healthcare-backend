"""Model-level behaviour and database constraints (the last line of defence)."""
import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.doctors.models import Doctor
from apps.mappings.models import PatientDoctorMapping
from apps.patients.models import Patient

User = get_user_model()

pytestmark = pytest.mark.django_db


class TestUserManager:
    def test_create_user_normalises_email_and_hashes_password(self):
        user = User.objects.create_user(email="  Mixed@Example.COM ", password="s3cret-Pass!", name="M")
        assert user.email == "mixed@example.com"
        assert user.password != "s3cret-Pass!"
        assert user.check_password("s3cret-Pass!")

    def test_regular_users_have_no_elevated_rights(self):
        user = User.objects.create_user(email="u@example.com", password="x", name="U")
        assert (user.is_staff, user.is_superuser, user.is_active) == (False, False, True)

    @pytest.mark.parametrize("email", ["", None])
    def test_email_is_required(self, email):
        with pytest.raises(ValueError, match="email"):
            User.objects.create_user(email=email, password="x", name="U")

    def test_create_superuser_sets_both_flags(self):
        admin = User.objects.create_superuser(email="root@example.com", password="x", name="Root")
        assert admin.is_staff and admin.is_superuser

    @pytest.mark.parametrize("flag", ["is_staff", "is_superuser"])
    def test_create_superuser_refuses_to_create_a_non_super_superuser(self, flag):
        with pytest.raises(ValueError, match="Superuser must have"):
            User.objects.create_superuser(email="r@example.com", password="x", name="R", **{flag: False})

    def test_save_lowercases_email_even_when_bypassing_the_manager(self):
        user = User(email="  UPPER@Example.com ", name="U")
        user.set_password("x")
        user.save()
        assert User.objects.get(pk=user.pk).email == "upper@example.com"

    def test_email_is_unique(self, user_factory):
        user_factory(email="dup@example.com")
        with pytest.raises(IntegrityError), transaction.atomic():
            user_factory(email="dup@example.com")

    def test_str_is_the_email(self, user_factory):
        assert str(user_factory(email="who@example.com")) == "who@example.com"


class TestDoctorConstraints:
    def test_email_unique_constraint_is_case_insensitive_at_database_level(self, doctor_factory):
        doctor_factory(email="Doc@Hospital.com")
        with pytest.raises(IntegrityError), transaction.atomic():
            # Bypasses the serializer on purpose: the DB must still refuse it.
            doctor_factory(email="doc@hospital.COM")

    def test_many_doctors_may_have_no_email(self, doctor_factory):
        doctor_factory(email="")
        doctor_factory(email="")
        assert Doctor.objects.filter(email="").count() == 2

    def test_creator_deletion_keeps_the_doctor(self, doctor_factory):
        doctor = doctor_factory()
        doctor.created_by.delete()
        doctor.refresh_from_db()
        assert doctor.created_by is None

    def test_experience_validator_range(self, doctor_factory):
        doctor = doctor_factory.build(years_of_experience=71)
        with pytest.raises(ValidationError) as exc_info:
            doctor.full_clean(exclude=["created_by"])
        assert "years_of_experience" in exc_info.value.message_dict

    def test_str(self, doctor_factory):
        assert str(doctor_factory(name="Asha", specialization="ENT")) == "Dr. Asha (ENT)"

    def test_default_ordering_is_by_name(self, doctor_factory):
        for name in ("Charlie", "Alpha", "Bravo"):
            doctor_factory(name=name)
        assert [d.name for d in Doctor.objects.all()] == ["Alpha", "Bravo", "Charlie"]


class TestPatientModel:
    def test_age_validator_upper_bound(self, patient_factory):
        patient = patient_factory.build(age=131)
        with pytest.raises(ValidationError) as exc_info:
            patient.full_clean(exclude=["created_by"])
        assert "age" in exc_info.value.message_dict

    def test_negative_age_is_rejected_by_the_database(self, patient_factory):
        with pytest.raises(IntegrityError), transaction.atomic():
            patient_factory(age=-1)

    def test_deleting_the_owner_deletes_their_patients(self, patient_factory):
        patient = patient_factory()
        patient.created_by.delete()
        assert not Patient.objects.filter(pk=patient.pk).exists()

    def test_timestamps_are_maintained_automatically(self, patient_factory):
        patient = patient_factory()
        created, first_update = patient.created_at, patient.updated_at
        patient.name = "Renamed"
        patient.save()
        patient.refresh_from_db()
        assert patient.created_at == created
        assert patient.updated_at > first_update

    def test_newest_first_ordering(self, patient_factory, alice):
        first = patient_factory(created_by=alice)
        second = patient_factory(created_by=alice)
        assert list(Patient.objects.filter(created_by=alice)) == [second, first]

    def test_str_includes_name_and_id(self, patient_factory):
        patient = patient_factory(name="Ravi")
        assert str(patient) == f"Ravi (#{patient.pk})"


class TestMappingConstraints:
    def test_pair_is_unique_at_database_level(self, mapping_factory):
        mapping = mapping_factory()
        with pytest.raises(IntegrityError), transaction.atomic():
            PatientDoctorMapping.objects.create(patient=mapping.patient, doctor=mapping.doctor)

    def test_same_doctor_for_different_patients_is_fine(self, mapping_factory, patient_factory):
        mapping = mapping_factory()
        PatientDoctorMapping.objects.create(patient=patient_factory(), doctor=mapping.doctor)
        assert PatientDoctorMapping.objects.filter(doctor=mapping.doctor).count() == 2

    def test_deleting_a_patient_cascades(self, mapping_factory):
        mapping = mapping_factory()
        mapping.patient.delete()
        assert not PatientDoctorMapping.objects.filter(pk=mapping.pk).exists()

    def test_deleting_a_doctor_cascades_but_keeps_the_patient(self, mapping_factory):
        mapping = mapping_factory()
        mapping.doctor.delete()
        assert not PatientDoctorMapping.objects.filter(pk=mapping.pk).exists()
        assert Patient.objects.filter(pk=mapping.patient_id).exists()

    def test_deleting_the_account_cascades_through_patients_to_mappings(self, mapping_factory):
        mapping = mapping_factory()
        mapping.patient.created_by.delete()
        assert not PatientDoctorMapping.objects.filter(pk=mapping.pk).exists()
        assert Doctor.objects.filter(pk=mapping.doctor_id).exists()

    def test_str(self, mapping_factory):
        mapping = mapping_factory()
        assert str(mapping) == f"{mapping.patient_id} -> {mapping.doctor_id}"

"""
factory_boy factories.

Values are sequence-based rather than random, so every failure is reproducible
and test data never collides with itself.
"""
import factory
from django.contrib.auth import get_user_model
from factory.django import DjangoModelFactory

from apps.doctors.models import Doctor
from apps.mappings.models import PatientDoctorMapping
from apps.patients.models import Patient

User = get_user_model()

DEFAULT_PASSWORD = "Str0ng!Pass#2026"


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    name = factory.Sequence(lambda n: f"User {n}")
    email = factory.Sequence(lambda n: f"user{n}@example.com")
    password = DEFAULT_PASSWORD

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        # Go through the manager so the password is hashed, as in production.
        return model_class.objects.create_user(*args, **kwargs)


class PatientFactory(DjangoModelFactory):
    class Meta:
        model = Patient

    name = factory.Sequence(lambda n: f"Patient {n}")
    age = 40
    gender = Patient.Gender.OTHER
    phone = "+919876543210"
    created_by = factory.SubFactory(UserFactory)


class DoctorFactory(DjangoModelFactory):
    class Meta:
        model = Doctor

    name = factory.Sequence(lambda n: f"Dr. Doctor {n}")
    specialization = "General Medicine"
    email = factory.Sequence(lambda n: f"doctor{n}@hospital.com")
    years_of_experience = 10
    created_by = factory.SubFactory(UserFactory)


class MappingFactory(DjangoModelFactory):
    class Meta:
        model = PatientDoctorMapping

    patient = factory.SubFactory(PatientFactory)
    doctor = factory.SubFactory(DoctorFactory)

from django_filters import rest_framework as filters

from .models import PatientDoctorMapping


class MappingFilter(filters.FilterSet):
    """
    Filter mappings by patient and/or doctor id.

    Plain numeric filters (rather than model-choice filters) on purpose: a
    choice filter validates the id against *all* patients, so an id belonging to
    another user would answer ``200 []`` while a nonexistent id would answer
    ``400``. That difference lets a caller probe which patient ids exist. With
    numeric filters both cases are simply an empty result.
    """

    patient = filters.NumberFilter(field_name="patient_id")
    doctor = filters.NumberFilter(field_name="doctor_id")

    class Meta:
        model = PatientDoctorMapping
        fields = ["patient", "doctor"]

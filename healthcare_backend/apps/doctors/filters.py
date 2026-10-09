from django_filters import rest_framework as filters

from .models import Doctor


class DoctorFilter(filters.FilterSet):
    specialization = filters.CharFilter(lookup_expr="iexact")
    min_experience = filters.NumberFilter(field_name="years_of_experience", lookup_expr="gte")

    class Meta:
        model = Doctor
        fields = ["specialization", "min_experience"]

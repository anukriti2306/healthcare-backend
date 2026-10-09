from django_filters import rest_framework as filters

from .models import Patient


class PatientFilter(filters.FilterSet):
    gender = filters.CharFilter(lookup_expr="iexact")
    min_age = filters.NumberFilter(field_name="age", lookup_expr="gte")
    max_age = filters.NumberFilter(field_name="age", lookup_expr="lte")

    class Meta:
        model = Patient
        fields = ["gender", "min_age", "max_age"]

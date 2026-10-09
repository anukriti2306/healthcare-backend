from rest_framework import viewsets

from .filters import PatientFilter
from .models import Patient
from .serializers import PatientSerializer


class PatientViewSet(viewsets.ModelViewSet):
    """
    CRUD for patients.

    A user can only ever see and change the patients they created. Records
    belonging to someone else behave as if they do not exist (404), so IDs of
    other users' patients are never revealed.
    """

    serializer_class = PatientSerializer
    lookup_value_regex = r"\d+"
    filterset_class = PatientFilter
    search_fields = ["name", "phone"]
    ordering_fields = ["name", "age", "created_at"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # schema generation
            return Patient.objects.none()
        return Patient.objects.filter(created_by=self.request.user)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

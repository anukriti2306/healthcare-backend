from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.core.permissions import IsCreatorOrReadOnly

from .filters import DoctorFilter
from .models import Doctor
from .serializers import DoctorSerializer


class DoctorViewSet(viewsets.ModelViewSet):
    """
    CRUD for doctors.

    Doctors form a shared directory: every authenticated user can list and
    read all of them, but only the user who added a doctor can edit or delete
    that record.
    """

    queryset = Doctor.objects.all()
    serializer_class = DoctorSerializer
    permission_classes = [IsAuthenticated, IsCreatorOrReadOnly]
    lookup_value_regex = r"\d+"
    filterset_class = DoctorFilter
    search_fields = ["name", "specialization", "email"]
    ordering_fields = ["name", "specialization", "years_of_experience", "created_at"]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

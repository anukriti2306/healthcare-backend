from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.patients.models import Patient

from .models import PatientDoctorMapping
from .serializers import MappingSerializer, PatientDoctorSerializer


def _user_mappings(user):
    """Mappings that belong to patients owned by `user`."""
    return PatientDoctorMapping.objects.filter(patient__created_by=user).select_related(
        "patient", "doctor"
    )


class MappingListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/mappings/  - all patient-doctor mappings of the current user's patients
    POST /api/mappings/  - assign a doctor to one of the current user's patients
    """

    serializer_class = MappingSerializer
    filterset_fields = ["patient", "doctor"]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # schema generation
            return PatientDoctorMapping.objects.none()
        return _user_mappings(self.request.user)


class MappingDetailView(APIView):
    """
    The same URL shape serves two purposes, as required by the API contract:

    GET    /api/mappings/<patient_id>/  - all doctors assigned to that patient
    DELETE /api/mappings/<mapping_id>/  - remove a doctor from a patient
    """

    @extend_schema(
        parameters=[OpenApiParameter("id", int, OpenApiParameter.PATH, description="Patient ID")],
        responses=PatientDoctorSerializer(many=True),
        summary="List doctors assigned to a patient",
        operation_id="mappings_doctors_of_patient",
    )
    def get(self, request, pk):
        patient = get_object_or_404(Patient.objects.filter(created_by=request.user), pk=pk)
        mappings = (
            PatientDoctorMapping.objects.filter(patient=patient)
            .select_related("doctor")
            .order_by("doctor__name", "id")
        )
        return Response(PatientDoctorSerializer(mappings, many=True).data)

    @extend_schema(
        parameters=[OpenApiParameter("id", int, OpenApiParameter.PATH, description="Mapping ID")],
        responses={204: None},
        summary="Remove a doctor from a patient",
        operation_id="mappings_remove_doctor",
    )
    def delete(self, request, pk):
        mapping = get_object_or_404(_user_mappings(request.user), pk=pk)
        mapping.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

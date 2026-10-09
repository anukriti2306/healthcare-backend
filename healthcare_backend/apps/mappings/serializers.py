from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator

from apps.doctors.serializers import DoctorSerializer
from apps.patients.models import Patient

from .models import PatientDoctorMapping


class MappingSerializer(serializers.ModelSerializer):
    """Create / list mappings: `{"patient": <id>, "doctor": <id>}`."""

    patient_name = serializers.CharField(source="patient.name", read_only=True)
    doctor_name = serializers.CharField(source="doctor.name", read_only=True)
    doctor_specialization = serializers.CharField(source="doctor.specialization", read_only=True)

    class Meta:
        model = PatientDoctorMapping
        fields = [
            "id",
            "patient",
            "patient_name",
            "doctor",
            "doctor_name",
            "doctor_specialization",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]
        extra_kwargs = {
            "patient": {"error_messages": {"does_not_exist": "Patient not found."}},
            "doctor": {"error_messages": {"does_not_exist": "Doctor not found."}},
        }
        validators = [
            UniqueTogetherValidator(
                queryset=PatientDoctorMapping.objects.all(),
                fields=["patient", "doctor"],
                message="This doctor is already assigned to this patient.",
            )
        ]

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        # A user may only assign doctors to patients they own. Other users'
        # patients are reported as "not found" so their IDs are not leaked.
        if request is not None and request.user.is_authenticated:
            fields["patient"].queryset = Patient.objects.filter(created_by=request.user)
        return fields


class PatientDoctorSerializer(serializers.ModelSerializer):
    """Doctors assigned to one patient: mapping id + full doctor details."""

    doctor = DoctorSerializer(read_only=True)

    class Meta:
        model = PatientDoctorMapping
        fields = ["id", "patient", "doctor", "created_at"]
        read_only_fields = fields

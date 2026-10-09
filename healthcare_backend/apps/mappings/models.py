from django.db import models

from apps.core.models import TimeStampedModel


class PatientDoctorMapping(TimeStampedModel):
    """Assignment of a doctor to a patient. A pair can only be assigned once."""

    patient = models.ForeignKey(
        "patients.Patient", on_delete=models.CASCADE, related_name="doctor_mappings"
    )
    doctor = models.ForeignKey(
        "doctors.Doctor", on_delete=models.CASCADE, related_name="patient_mappings"
    )

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["patient", "doctor"], name="unique_patient_doctor_mapping"
            )
        ]

    def __str__(self):
        return f"{self.patient_id} -> {self.doctor_id}"

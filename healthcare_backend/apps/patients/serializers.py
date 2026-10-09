from rest_framework import serializers

from .models import Patient

GENDER_ALIASES = {
    "m": Patient.Gender.MALE,
    "male": Patient.Gender.MALE,
    "f": Patient.Gender.FEMALE,
    "female": Patient.Gender.FEMALE,
    "o": Patient.Gender.OTHER,
    "other": Patient.Gender.OTHER,
}


class PatientSerializer(serializers.ModelSerializer):
    gender = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=10,
        help_text="One of: male, female, other (also accepts M / F / O, any case).",
    )

    class Meta:
        model = Patient
        fields = [
            "id",
            "name",
            "age",
            "gender",
            "phone",
            "address",
            "medical_history",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]

    def validate_gender(self, value):
        if not value:
            return ""
        try:
            return GENDER_ALIASES[value.strip().lower()].value
        except KeyError:
            raise serializers.ValidationError("Must be one of: male, female, other.") from None

from django.conf import settings
from django.core.validators import MaxValueValidator
from django.db import models

from apps.core.models import TimeStampedModel
from apps.core.validators import phone_validator


class Patient(TimeStampedModel):
    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        OTHER = "other", "Other"

    name = models.CharField(max_length=150)
    age = models.PositiveSmallIntegerField(validators=[MaxValueValidator(130)])
    gender = models.CharField(max_length=10, choices=Gender.choices, blank=True)
    phone = models.CharField(max_length=20, blank=True, validators=[phone_validator])
    address = models.TextField(blank=True)
    medical_history = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="patients",
    )

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["created_by", "-created_at"])]

    def __str__(self):
        return f"{self.name} (#{self.pk})"

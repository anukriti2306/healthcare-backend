from django.conf import settings
from django.core.validators import MaxValueValidator
from django.db import models
from django.db.models.functions import Lower

from apps.core.models import TimeStampedModel
from apps.core.validators import phone_validator


class Doctor(TimeStampedModel):
    name = models.CharField(max_length=150)
    specialization = models.CharField(max_length=100)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True, validators=[phone_validator])
    years_of_experience = models.PositiveSmallIntegerField(
        default=0, validators=[MaxValueValidator(70)]
    )
    # Doctors are a shared directory, so they survive the deletion of the
    # account that added them.
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="doctors",
    )

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            # Case-insensitive unique email (only when an email is provided).
            models.UniqueConstraint(
                Lower("email"),
                condition=~models.Q(email=""),
                name="doctor_unique_email_ci",
            )
        ]

    def __str__(self):
        return f"Dr. {self.name} ({self.specialization})"

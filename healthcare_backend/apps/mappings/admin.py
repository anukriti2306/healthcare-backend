from django.contrib import admin

from .models import PatientDoctorMapping


@admin.register(PatientDoctorMapping)
class PatientDoctorMappingAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "doctor", "created_at")
    search_fields = ("patient__name", "doctor__name")
    autocomplete_fields = ("patient", "doctor")

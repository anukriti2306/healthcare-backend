from django.contrib import admin

from .models import Doctor


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "specialization", "email", "years_of_experience", "created_by")
    list_filter = ("specialization",)
    search_fields = ("name", "specialization", "email")
    autocomplete_fields = ("created_by",)

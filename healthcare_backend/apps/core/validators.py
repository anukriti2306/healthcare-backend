from django.core.validators import RegexValidator

phone_validator = RegexValidator(
    regex=r"^\+?[0-9][0-9\s\-]{5,18}[0-9]$",
    message="Enter a valid phone number (7-20 characters: digits, an optional leading '+', spaces or hyphens).",
)

from django.core.validators import RegexValidator

phone_validator = RegexValidator(
    # Explicit space (not \s, which also matches tabs/newlines) and \Z (not $,
    # which tolerates a trailing newline).
    regex=r"^\+?[0-9][0-9 \-]{5,18}[0-9]\Z",
    message="Enter a valid phone number (7-20 characters: digits, an optional leading '+', spaces or hyphens).",
)

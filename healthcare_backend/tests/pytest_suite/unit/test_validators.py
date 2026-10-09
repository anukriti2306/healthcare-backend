"""Unit tests for apps.core.validators.phone_validator."""
import pytest
from django.core.exceptions import ValidationError

from apps.core.validators import phone_validator


@pytest.mark.parametrize(
    "number",
    [
        pytest.param("9876543", id="shortest-7-chars"),
        pytest.param("+919876543210", id="e164"),
        pytest.param("+91 98765 43210", id="spaces"),
        pytest.param("080-2345-6789", id="hyphens"),
        pytest.param("+91 80 2345 6789", id="mixed-separators"),
        pytest.param("1" * 20, id="longest-20-digits"),
    ],
)
def test_accepts_valid_numbers(number):
    phone_validator(number)  # must not raise


@pytest.mark.parametrize(
    "number",
    [
        pytest.param("", id="empty"),
        pytest.param("123456", id="too-short-6"),
        pytest.param("1" * 21, id="too-long-21-digits"),
        pytest.param("call me maybe", id="letters"),
        pytest.param("+", id="plus-only"),
        pytest.param("++919876543210", id="double-plus"),
        pytest.param("9198765+43210", id="plus-in-the-middle"),
        pytest.param("-9876543210", id="leading-hyphen"),
        pytest.param("98765 43210-", id="trailing-separator"),
        pytest.param("(080) 2345 6789", id="parentheses-not-supported"),
        pytest.param("98765\n43210", id="newline-inside"),
        pytest.param("9876543210\n", id="trailing-newline"),
        pytest.param("98765\t43210", id="tab"),
    ],
)
def test_rejects_invalid_numbers(number):
    with pytest.raises(ValidationError):
        phone_validator(number)

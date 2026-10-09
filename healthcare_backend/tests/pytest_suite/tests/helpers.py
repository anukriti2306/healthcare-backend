"""Small, dependency-free helpers shared by the test modules."""
from tests.factories import DEFAULT_PASSWORD

PASSWORD = DEFAULT_PASSWORD


def assert_error(response, status_code, code=None):
    """
    Assert that ``response`` follows the project-wide error envelope::

        {"error": {"status": int, "code": str, "message": str, ["details": ...]}}

    and return the inner ``error`` dict for further assertions.
    """
    assert response.status_code == status_code, response.content
    body = response.json()
    assert set(body) == {"error"}, f"unexpected top-level keys: {set(body)}"
    error = body["error"]
    assert set(error) <= {"status", "code", "message", "details"}
    assert error["status"] == status_code
    assert isinstance(error["message"], str) and error["message"]
    # `details` is documented as validation-only.
    assert ("details" in error) == (error["code"] == "validation_error")
    if code is not None:
        assert error["code"] == code
    return error


def patient_payload(**overrides):
    data = {
        "name": "John Doe",
        "age": 42,
        "gender": "male",
        "phone": "+91 98765 43210",
        "address": "12 MG Road, Bengaluru",
        "medical_history": "Hypertension",
    }
    data.update(overrides)
    return data


def doctor_payload(**overrides):
    data = {
        "name": "Dr. Asha Rao",
        "specialization": "Cardiology",
        "email": "asha.rao@hospital.com",
        "phone": "+91 80 2345 6789",
        "years_of_experience": 12,
    }
    data.update(overrides)
    return data


def names(response):
    """Names from a list response, in order."""
    return [item["name"] for item in response.json()]

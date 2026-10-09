"""Serializer logic exercised without the HTTP layer."""
import pytest

from apps.accounts.serializers import LoginSerializer, RegisterSerializer
from apps.patients.serializers import GENDER_ALIASES, PatientSerializer
from tests.helpers import PASSWORD

pytestmark = pytest.mark.django_db


class TestPatientGenderNormalisation:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("m", "male"), ("M", "male"), (" Male ", "male"), ("F", "female"),
         ("FEMALE", "female"), ("o", "other"), ("Other", "other"), ("", "")],
    )
    def test_valid_inputs(self, raw, expected):
        assert PatientSerializer().validate_gender(raw) == expected

    @pytest.mark.parametrize("raw", ["x", "robot", "maleee", "mf"])
    def test_invalid_inputs(self, raw):
        from rest_framework.exceptions import ValidationError

        with pytest.raises(ValidationError):
            PatientSerializer().validate_gender(raw)

    def test_every_alias_maps_to_a_real_choice(self):
        # Guards against adding an alias that the model's choices would reject.
        from apps.patients.models import Patient

        assert {v.value for v in GENDER_ALIASES.values()} <= set(Patient.Gender.values)


class TestRegisterSerializer:
    def test_valid_payload_creates_a_user(self):
        serializer = RegisterSerializer(data={"name": "Carol", "email": "Carol@Example.com", "password": PASSWORD})
        assert serializer.is_valid(), serializer.errors
        user = serializer.save()
        assert user.email == "carol@example.com"

    def test_password_is_write_only(self):
        serializer = RegisterSerializer(data={"name": "C", "email": "c@example.com", "password": PASSWORD})
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        assert "password" not in RegisterSerializer(user).data

    def test_password_similar_to_email_is_rejected(self):
        serializer = RegisterSerializer(
            data={"name": "Carol", "email": "carol@example.com", "password": "carol@example.com"}
        )
        assert not serializer.is_valid()
        assert "password" in serializer.errors


class TestLoginSerializer:
    def test_token_embeds_name_and_email_claims(self, alice):
        token = LoginSerializer.get_token(alice)
        assert token["name"] == "Alice"
        assert token["email"] == "alice@example.com"
        assert token["user_id"] == str(alice.id)

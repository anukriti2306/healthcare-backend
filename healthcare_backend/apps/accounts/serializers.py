from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "name", "email", "date_joined"]
        read_only_fields = fields


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True, trim_whitespace=False, style={"input_type": "password"}
    )

    class Meta:
        model = User
        fields = ["id", "name", "email", "password"]
        read_only_fields = ["id"]
        # Uniqueness is checked case-insensitively in validate_email below.
        extra_kwargs = {"email": {"validators": []}}

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate(self, attrs):
        # Run Django's password validators with the candidate user so the
        # "too similar to your email/name" check works.
        candidate = User(email=attrs["email"], name=attrs["name"])
        try:
            validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)}) from exc
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class LoginSerializer(TokenObtainPairSerializer):
    """Email + password -> access/refresh JWT pair (plus basic user info)."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["name"] = user.name
        token["email"] = user.email
        return token

    def validate(self, attrs):
        attrs[self.username_field] = attrs[self.username_field].strip().lower()
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user).data
        return data


# --- Response shapes, used only for the OpenAPI documentation ---------------
class TokenPairSerializer(serializers.Serializer):
    refresh = serializers.CharField()
    access = serializers.CharField()


class RegisterResponseSerializer(serializers.Serializer):
    user = UserSerializer()
    tokens = TokenPairSerializer()


class LoginResponseSerializer(TokenPairSerializer):
    user = UserSerializer()

from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .serializers import (
    LoginResponseSerializer,
    LoginSerializer,
    RegisterResponseSerializer,
    RegisterSerializer,
    UserSerializer,
)


class PublicAuthMixin:
    """
    Settings shared by the unauthenticated auth endpoints.

    ``authentication_classes = []`` means a stale/invalid ``Authorization``
    header can never make a login or register call fail.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


class RegisterView(PublicAuthMixin, generics.GenericAPIView):
    """Register a new user with name, email and password."""

    serializer_class = RegisterSerializer

    @extend_schema(responses={201: RegisterResponseSerializer})
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "user": UserSerializer(user).data,
                "tokens": {"refresh": str(refresh), "access": str(refresh.access_token)},
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(PublicAuthMixin, TokenObtainPairView):
    """Log in with email + password and receive a JWT access/refresh pair."""

    serializer_class = LoginSerializer

    @extend_schema(responses={200: LoginResponseSerializer})
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class TokenRefreshThrottledView(PublicAuthMixin, TokenRefreshView):
    """Exchange a refresh token for a new access token."""


class MeView(generics.RetrieveAPIView):
    """Return the currently authenticated user."""

    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user

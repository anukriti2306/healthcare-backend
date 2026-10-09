"""Root URL configuration."""
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.core.views import health_check

handler404 = "apps.core.views.not_found"
handler500 = "apps.core.views.server_error"

urlpatterns = [
    path("admin/", admin.site.urls),
    # Operations
    path("api/health/", health_check, name="health"),
    # API documentation (OpenAPI 3 + Swagger UI)
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    # Resources
    path("api/auth/", include("apps.accounts.urls")),
    path("api/", include("apps.patients.urls")),
    path("api/", include("apps.doctors.urls")),
    path("api/mappings/", include("apps.mappings.urls")),
]

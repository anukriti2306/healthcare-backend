from django.urls import path

from .views import MappingDetailView, MappingListCreateView

urlpatterns = [
    path("", MappingListCreateView.as_view(), name="mapping-list"),
    path("<int:pk>/", MappingDetailView.as_view(), name="mapping-detail"),
]

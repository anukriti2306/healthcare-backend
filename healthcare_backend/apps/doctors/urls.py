from rest_framework.routers import SimpleRouter

from .views import DoctorViewSet

router = SimpleRouter()
router.register("doctors", DoctorViewSet, basename="doctor")

urlpatterns = router.urls

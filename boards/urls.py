from rest_framework.routers import DefaultRouter

from .views import BoardViewSet

router = DefaultRouter()
router.register("boards", BoardViewSet, basename="board")

urlpatterns = router.urls

from rest_framework.routers import DefaultRouter

from .views import BoardViewSet, CardViewSet

router = DefaultRouter()
router.register("boards", BoardViewSet, basename="board")
router.register("cards", CardViewSet, basename="card")

urlpatterns = router.urls

from rest_framework.routers import DefaultRouter

from .views import BoardViewSet, CardViewSet, CommentViewSet

router = DefaultRouter()
router.register("boards", BoardViewSet, basename="board")
router.register("cards", CardViewSet, basename="card")
router.register("comments", CommentViewSet, basename="comment")

urlpatterns = router.urls

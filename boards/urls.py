from rest_framework.routers import DefaultRouter

from .views import BoardViewSet, CommentViewSet, WorkItemViewSet

router = DefaultRouter()
router.register("boards", BoardViewSet, basename="board")
router.register("work-items", WorkItemViewSet, basename="work-item")
router.register("comments", CommentViewSet, basename="comment")

urlpatterns = router.urls

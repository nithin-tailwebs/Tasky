from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import BoardViewSet, CommentViewSet, ComponentViewSet, WorkItemViewSet

router = DefaultRouter()
router.register("boards", BoardViewSet, basename="board")
router.register("work-items", WorkItemViewSet, basename="work-item")
router.register("comments", CommentViewSet, basename="comment")

urlpatterns = router.urls + [
    path(
        "projects/<int:project_pk>/components/",
        ComponentViewSet.as_view({"get": "list", "post": "create"}),
        name="project-components",
    ),
    path(
        "projects/<int:project_pk>/components/<int:pk>/",
        ComponentViewSet.as_view({"patch": "partial_update", "delete": "destroy"}),
        name="project-component-detail",
    ),
]

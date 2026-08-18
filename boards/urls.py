from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    BoardViewSet,
    CommentViewSet,
    ComponentViewSet,
    CustomFieldViewSet,
    FieldOptionViewSet,
    WorkItemLinkViewSet,
    WorkItemViewSet,
)

router = DefaultRouter()
router.register("boards", BoardViewSet, basename="board")
router.register("work-items", WorkItemViewSet, basename="work-item")
router.register("comments", CommentViewSet, basename="comment")
router.register("work-item-links", WorkItemLinkViewSet, basename="work-item-link")
router.register("fields", CustomFieldViewSet, basename="custom-field")

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
    path(
        "fields/<int:field_pk>/options/",
        FieldOptionViewSet.as_view({"post": "create"}),
        name="field-options",
    ),
    path(
        "fields/<int:field_pk>/options/<int:pk>/",
        FieldOptionViewSet.as_view({"patch": "partial_update", "delete": "destroy"}),
        name="field-option-detail",
    ),
]

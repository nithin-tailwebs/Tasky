from rest_framework.routers import DefaultRouter

from .views import InvitationViewSet, ProjectViewSet

router = DefaultRouter()
router.register("projects", ProjectViewSet, basename="project")
router.register("invitations", InvitationViewSet, basename="invitation")

urlpatterns = router.urls

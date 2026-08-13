from rest_framework import mixins, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated

from .models import Project, ProjectMembership
from .permissions import IsProjectMember, can_delete_project
from .serializers import ProjectSerializer


class ProjectViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated, IsProjectMember]
    pagination_class = None

    def get_queryset(self):
        qs = Project.objects.all()
        if self.action == "list":
            qs = qs.filter(memberships__user=self.request.user).distinct()
        return qs

    def perform_create(self, serializer):
        project = serializer.save()
        ProjectMembership.objects.create(
            project=project, user=self.request.user, role=ProjectMembership.Role.OWNER
        )

    def perform_destroy(self, instance):
        membership = instance.memberships.get(user=self.request.user)
        if not can_delete_project(membership.role):
            raise PermissionDenied("Only the owner can delete a project.")
        instance.delete()

from django.shortcuts import get_object_or_404
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Project, ProjectMembership
from .permissions import IsProjectMember, can_change_role, can_delete_project, can_leave, can_remove
from .serializers import ChangeRoleSerializer, ProjectMembershipSerializer, ProjectSerializer

ROLE_ORDER = {"owner": 0, "admin": 1, "member": 2}


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

    @action(detail=True, methods=["get"], url_path="members")
    def members(self, request, pk=None):
        project = self.get_object()
        memberships = sorted(
            project.memberships.select_related("user"),
            key=lambda m: (ROLE_ORDER[m.role], m.id),
        )
        return Response(ProjectMembershipSerializer(memberships, many=True).data)

    @action(detail=True, methods=["delete"], url_path=r"members/(?P<user_id>[^/.]+)")
    def remove_member(self, request, pk=None, user_id=None):
        """Doubles as "leave": removing your own membership is only ever
        blocked for the Owner (who must transfer ownership first). Removing
        someone else goes through the normal can_remove role matrix."""
        project = self.get_object()
        acting = project.memberships.get(user=request.user)
        target = get_object_or_404(ProjectMembership, project=project, user_id=user_id)

        if target.user_id == request.user.id:
            if not can_leave(acting.role):
                raise ValidationError(
                    {"detail": "Transfer ownership before leaving a project you own."}
                )
            target.delete()
            return Response(status=204)

        if not can_remove(acting.role, target.role):
            raise PermissionDenied("You don't have permission to remove this member.")

        target.delete()
        return Response(status=204)

    @action(detail=True, methods=["post"], url_path=r"members/(?P<user_id>[^/.]+)/role")
    def change_role(self, request, pk=None, user_id=None):
        project = self.get_object()
        acting = project.memberships.get(user=request.user)
        if not can_change_role(acting.role):
            raise PermissionDenied("Only the owner can change member roles.")

        serializer = ChangeRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        target = get_object_or_404(ProjectMembership, project=project, user_id=user_id)
        if target.role == ProjectMembership.Role.OWNER:
            raise PermissionDenied(
                "The owner's role can't be changed here — transfer ownership instead."
            )
        target.role = serializer.validated_data["role"]
        target.save()
        return Response(ProjectMembershipSerializer(target).data)

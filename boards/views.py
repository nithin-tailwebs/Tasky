from django.db import transaction
from django.http import Http404
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from projects.models import Project, ProjectMembership
from projects.permissions import IsProjectMember

from .models import Board, Comment, WorkItem
from .serializers import (
    BoardSerializer,
    CommentSerializer,
    MoveWorkItemSerializer,
    WorkItemSerializer,
    WorkItemSummarySerializer,
)
from .services import move_work_item, next_position


class BoardViewSet(viewsets.ModelViewSet):
    """Boards are scoped to the projects a person belongs to."""

    serializer_class = BoardSerializer
    pagination_class = None
    permission_classes = [IsAuthenticated, IsProjectMember]

    def get_queryset(self):
        qs = Board.objects.select_related("project", "created_by")
        if self.action == "list":
            qs = qs.filter(
                project_id__in=ProjectMembership.objects.filter(
                    user=self.request.user
                ).values_list("project_id", flat=True)
            )
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def update(self, request, *args, **kwargs):
        # Boards do not move between projects — same "echo-back-unchanged-is-
        # fine, a real change is rejected" rule WorkItem already applies to
        # status/board.
        if "project" in request.data:
            board = self.get_object()
            if str(request.data["project"]) != str(board.project_id):
                raise ValidationError({"project": "Boards cannot be moved between projects."})
        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=["get"], url_path="work-items")
    def work_items(self, request, pk=None):
        board = self.get_object()
        items = board.work_items.select_related("assignee", "created_by")
        return Response(WorkItemSerializer(items, many=True).data)


class WorkItemViewSet(viewsets.ModelViewSet):
    serializer_class = WorkItemSerializer
    pagination_class = None
    permission_classes = [IsAuthenticated, IsProjectMember]

    def get_queryset(self):
        qs = WorkItem.objects.select_related("board__project", "assignee", "created_by")
        if self.action == "list":
            qs = qs.filter(
                board__project_id__in=ProjectMembership.objects.filter(
                    user=self.request.user
                ).values_list("project_id", flat=True)
            )
        return qs

    def perform_create(self, serializer):
        board = serializer.validated_data["board"]
        status = serializer.validated_data.get("status", WorkItem.Status.TODO)
        with transaction.atomic():
            project = Project.objects.select_for_update().get(pk=board.project_id)
            key = f"{project.key}-{project.next_item_number}"
            project.next_item_number += 1
            project.save(update_fields=["next_item_number"])
            serializer.save(
                key=key,
                created_by=self.request.user,
                position=next_position(board.id, status),
            )

    def update(self, request, *args, **kwargs):
        # Covers both PUT and PATCH: UpdateModelMixin.partial_update() just
        # calls this with partial=True. An actual status CHANGE here would
        # move the item between columns with NO renumbering — the source
        # keeps a gap, the destination gets a duplicate position — so that's
        # rejected in favour of the one route that renumbers correctly.
        # Only a real change is rejected: a UI that PATCHes back the full set
        # of fields it's holding (status included, unchanged, alongside a
        # genuine edit like title) must not have that legitimate edit 400'd
        # just because the status key was present in the body.
        # Same defect, same fix, for board: relocating an item to a different
        # board with a plain PATCH would leave a gap in the source column's
        # positions and a duplicate position in the destination column — no
        # renumbering happens either side. Work items do not move between
        # boards in this product at all, so unlike status there is no
        # endpoint to redirect to; a real change is just rejected outright.
        if "status" in request.data or "board" in request.data or "item_type" in request.data or "key" in request.data:
            item = self.get_object()
            if "status" in request.data and request.data["status"] != item.status:
                raise ValidationError(
                    {
                        "status": (
                            "Status cannot be changed here — "
                            "POST to /api/work-items/{id}/move/ instead."
                        )
                    }
                )
            if "board" in request.data and str(request.data["board"]) != str(item.board_id):
                raise ValidationError(
                    {
                        "board": "Work items cannot be moved between boards."
                    }
                )
            if "item_type" in request.data and request.data["item_type"] != item.item_type:
                raise ValidationError({"item_type": "Type cannot be changed after creation."})
            if "key" in request.data and request.data["key"] != item.key:
                raise ValidationError({"key": "Key cannot be changed."})
        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def move(self, request, pk=None):
        item = self.get_object()

        serializer = MoveWorkItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            move_work_item(
                item,
                serializer.validated_data["status"],
                serializer.validated_data["position"],
            )
        except WorkItem.DoesNotExist:
            # The item was deleted by another request between this request's
            # (unlocked) get_object() and move_work_item()'s row lock.
            # WorkItem.DoesNotExist is not converted to 404 by DRF's default
            # exception handler on its own (only django.http.Http404 and
            # PermissionDenied are) — it has to be translated explicitly, or
            # this would surface as a 500.
            raise Http404("Work item was deleted before the move could be applied.")
        item.refresh_from_db()
        return Response(WorkItemSerializer(item).data)

    @action(detail=True, methods=["get"])
    def children(self, request, pk=None):
        item = self.get_object()
        return Response(WorkItemSummarySerializer(item.children.all(), many=True).data)

    @action(detail=True, methods=["get", "post"])
    def comments(self, request, pk=None):
        item = self.get_object()

        if request.method == "POST":
            serializer = CommentSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save(card=item, author=request.user)
            return Response(serializer.data, status=201)

        thread = item.comments.select_related("author")
        return Response(CommentSerializer(thread, many=True).data)


class CommentViewSet(mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """Deletion only — comments are created through the work item's own endpoint."""

    serializer_class = CommentSerializer
    permission_classes = [IsAuthenticated, IsProjectMember]

    def get_queryset(self):
        return Comment.objects.select_related("author", "card__board__project")

    def perform_destroy(self, instance):
        # An authorless comment (its author's account was deleted, which
        # SET_NULLs this FK) must not become permanently undeletable.
        # `instance.author != self.request.user` is True for EVERY signed-in
        # user when author is None, which would brick deletion for good —
        # so ownership is only enforced when there is an owner to enforce.
        if instance.author_id is not None and instance.author != self.request.user:
            raise PermissionDenied("You can only delete your own comments.")
        instance.delete()

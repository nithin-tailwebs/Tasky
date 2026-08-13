from django.http import Http404
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from projects.models import ProjectMembership

from .models import Board, Card, Comment
from .serializers import (
    BoardSerializer,
    CardSerializer,
    CommentSerializer,
    MoveCardSerializer,
)
from .services import move_card, next_position


class BoardViewSet(viewsets.ModelViewSet):
    """Boards are scoped to the projects a person belongs to."""

    serializer_class = BoardSerializer
    pagination_class = None

    def get_queryset(self):
        qs = Board.objects.select_related("created_by")
        if self.action == "list":
            qs = qs.filter(
                project_id__in=ProjectMembership.objects.filter(
                    user=self.request.user
                ).values_list("project_id", flat=True)
            )
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["get"])
    def cards(self, request, pk=None):
        board = self.get_object()
        cards = board.cards.select_related("assignee", "created_by")
        return Response(CardSerializer(cards, many=True).data)


class CardViewSet(viewsets.ModelViewSet):
    queryset = Card.objects.select_related("board", "assignee", "created_by")
    serializer_class = CardSerializer
    pagination_class = None

    def perform_create(self, serializer):
        board = serializer.validated_data["board"]
        status = serializer.validated_data.get("status", Card.Status.TODO)
        serializer.save(
            created_by=self.request.user,
            position=next_position(board.id, status),
        )

    def update(self, request, *args, **kwargs):
        # Covers both PUT and PATCH: UpdateModelMixin.partial_update() just
        # calls this with partial=True. An actual status CHANGE here would
        # move the card between columns with NO renumbering — the source
        # keeps a gap, the destination gets a duplicate position — so that's
        # rejected in favour of the one route that renumbers correctly.
        # Only a real change is rejected: a UI that PATCHes back the full set
        # of fields it's holding (status included, unchanged, alongside a
        # genuine edit like title) must not have that legitimate edit 400'd
        # just because the status key was present in the body.
        # Same defect, same fix, for board: relocating a card to a different
        # board with a plain PATCH would leave a gap in the source column's
        # positions and a duplicate position in the destination column — no
        # renumbering happens either side. Cards do not move between boards
        # in this product at all, so unlike status there is no endpoint to
        # redirect to; a real change is just rejected outright. As with
        # status, a PATCH that echoes back the card's current, unchanged
        # board alongside a genuine edit (e.g. title) must not be 400'd.
        if "status" in request.data or "board" in request.data:
            card = self.get_object()
            if "status" in request.data and request.data["status"] != card.status:
                raise ValidationError(
                    {
                        "status": (
                            "Status cannot be changed here — "
                            "POST to /api/cards/{id}/move/ instead."
                        )
                    }
                )
            if "board" in request.data and str(request.data["board"]) != str(card.board_id):
                raise ValidationError(
                    {
                        "board": "Cards cannot be moved between boards."
                    }
                )
        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def move(self, request, pk=None):
        card = self.get_object()

        serializer = MoveCardSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            move_card(
                card,
                serializer.validated_data["status"],
                serializer.validated_data["position"],
            )
        except Card.DoesNotExist:
            # The card was deleted by another request between this request's
            # (unlocked) get_object() and move_card()'s row lock. Card.DoesNotExist
            # is not converted to 404 by DRF's default exception handler on its
            # own (only django.http.Http404 and PermissionDenied are) — it has to
            # be translated explicitly, or this would surface as a 500.
            raise Http404("Card was deleted before the move could be applied.")
        card.refresh_from_db()
        return Response(CardSerializer(card).data)

    @action(detail=True, methods=["get", "post"])
    def comments(self, request, pk=None):
        card = self.get_object()

        if request.method == "POST":
            serializer = CommentSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save(card=card, author=request.user)
            return Response(serializer.data, status=201)

        thread = card.comments.select_related("author")
        return Response(CommentSerializer(thread, many=True).data)


class CommentViewSet(mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """Deletion only — comments are created through the card's own endpoint."""

    queryset = Comment.objects.select_related("author")
    serializer_class = CommentSerializer

    def perform_destroy(self, instance):
        # An authorless comment (its author's account was deleted, which
        # SET_NULLs this FK) must not become permanently undeletable.
        # `instance.author != self.request.user` is True for EVERY signed-in
        # user when author is None, which would brick deletion for good —
        # so ownership is only enforced when there is an owner to enforce.
        if instance.author_id is not None and instance.author != self.request.user:
            raise PermissionDenied("You can only delete your own comments.")
        instance.delete()

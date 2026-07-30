from django.http import Http404
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .models import Board, Card
from .serializers import BoardSerializer, CardSerializer, MoveCardSerializer
from .services import move_card, next_position


class BoardViewSet(viewsets.ModelViewSet):
    """Every signed-in person sees every board — the team is small and shares its work."""

    queryset = Board.objects.select_related("created_by")
    serializer_class = BoardSerializer
    pagination_class = None

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
        if "status" in request.data:
            card = self.get_object()
            if request.data["status"] != card.status:
                raise ValidationError(
                    {
                        "status": (
                            "Status cannot be changed here — "
                            "POST to /api/cards/{id}/move/ instead."
                        )
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

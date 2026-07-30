from rest_framework import viewsets
from rest_framework.decorators import action
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

    @action(detail=True, methods=["post"])
    def move(self, request, pk=None):
        card = self.get_object()

        serializer = MoveCardSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        move_card(
            card,
            serializer.validated_data["status"],
            serializer.validated_data["position"],
        )
        card.refresh_from_db()
        return Response(CardSerializer(card).data)

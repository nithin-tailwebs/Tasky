from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Board, Card
from .serializers import BoardSerializer, CardSerializer
from .services import next_position


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

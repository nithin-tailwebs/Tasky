from rest_framework import viewsets

from .models import Board
from .serializers import BoardSerializer


class BoardViewSet(viewsets.ModelViewSet):
    """Every signed-in person sees every board — the team is small and shares its work."""

    queryset = Board.objects.select_related("created_by")
    serializer_class = BoardSerializer
    pagination_class = None

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

from django.db.models import F
from rest_framework.generics import ListAPIView

from .models import Card
from .serializers import CardSerializer


class MyTasksView(ListAPIView):
    """Everything assigned to me that is still open, soonest deadline first."""

    serializer_class = CardSerializer
    pagination_class = None

    def get_queryset(self):
        return (
            Card.objects.filter(assignee=self.request.user)
            .exclude(status=Card.Status.DONE)
            .select_related("board", "assignee", "created_by")
            .order_by(F("due_date").asc(nulls_last=True), "-priority", "id")
        )

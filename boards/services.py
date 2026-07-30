from django.db.models import Max

from .models import Card


def next_position(board_id: int, status: str) -> int:
    """The position a new card takes: the end of its column."""
    highest = Card.objects.filter(board_id=board_id, status=status).aggregate(
        highest=Max("position")
    )["highest"]
    return 0 if highest is None else highest + 1

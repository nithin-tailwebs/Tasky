from django.db import transaction
from django.db.models import Max

from .models import Card


def next_position(board_id: int, status: str) -> int:
    """The position a new card takes: the end of its column."""
    highest = Card.objects.filter(board_id=board_id, status=status).aggregate(
        highest=Max("position")
    )["highest"]
    return 0 if highest is None else highest + 1


@transaction.atomic
def move_card(card: Card, new_status: str, new_position: int) -> Card:
    """Drop a card into a column at a position, then renumber the affected columns.

    Every card on the board is locked, in a stable id order. That is heavier than
    locking two columns, but a board holds tens of rows, and a consistent lock order
    is what stops two simultaneous drags deadlocking each other.
    """
    locked = list(
        Card.objects.select_for_update()
        .filter(board_id=card.board_id)
        .order_by("id")
    )

    old_status = card.status
    card.status = new_status

    def renumber(status: str) -> list[Card]:
        column = [c for c in locked if c.status == status and c.pk != card.pk]
        column.sort(key=lambda c: (c.position, c.pk))

        if status == new_status:
            index = max(0, min(new_position, len(column)))
            column.insert(index, card)

        for index, member in enumerate(column):
            member.position = index
        return column

    touched = renumber(new_status)
    if old_status != new_status:
        touched += renumber(old_status)

    Card.objects.bulk_update(touched, ["position", "status"])
    return card

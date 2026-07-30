from django.db import transaction
from django.db.models import Max
from django.utils import timezone

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

    Every card on the board is locked with SELECT ... FOR UPDATE. That is heavier
    than locking two columns, but a board holds tens of rows, and it buys real
    safety: two concurrent moves on the SAME board issue the identical
    `WHERE board_id = ?` predicate against the same index, so both transactions
    scan (and therefore lock) the rows in the same order — that shared
    predicate/index is what makes them serialise instead of deadlocking. The
    trailing `order_by("id")` is a filesort applied to rows that are already
    locked by then; it gives the renumbering a stable, deterministic order to
    read in, but it plays no part in lock acquisition and is NOT what prevents
    the deadlock. Moves on different boards lock disjoint row sets and never
    contend at all. Do not narrow this to a two-column lock on the theory that
    the ORDER BY protects it — it doesn't; any narrower filter would need its
    own argument for why it stays deadlock-free.
    """
    locked = list(
        Card.objects.select_for_update()
        .filter(board_id=card.board_id)
        .order_by("id")
    )

    locked_by_pk = {c.pk: c for c in locked}
    if card.pk not in locked_by_pk:
        # `card` was fetched (unlocked) by the view before this transaction
        # took the lock. If another request deleted it in between, trusting
        # `card.status` here would use a stale, possibly-wrong old_status
        # (breaking the 0..n-1 invariant on whichever column it actually left),
        # and inserting `card` into the destination column would resurrect a
        # ghost row that bulk_update never writes, leaving the destination
        # with a hole. Surface it as "gone" instead.
        raise Card.DoesNotExist(
            f"Card {card.pk} was deleted before the move could be applied."
        )

    old_status = locked_by_pk[card.pk].status
    card.status = new_status

    def renumber(status: str) -> list[Card]:
        column = [c for c in locked if c.status == status and c.pk != card.pk]
        column.sort(key=lambda c: (c.position, c.pk))

        if status == new_status:
            index = max(0, min(new_position, len(column)))
            column.insert(index, card)

        now = timezone.now()
        for index, member in enumerate(column):
            member.position = index
            member.updated_at = now
        return column

    touched = renumber(new_status)
    if old_status != new_status:
        touched += renumber(old_status)

    Card.objects.bulk_update(touched, ["position", "status", "updated_at"])
    return card

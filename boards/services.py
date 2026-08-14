from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from .models import WorkItem


def next_position(board_id: int, status: str) -> int:
    """The position a new work item takes: the end of its column.

    This read is deliberately UNLOCKED. Two concurrent creates into the
    same column can both read the same Max(position) and both save with
    that same position — that duplicate is a real possible outcome, not a
    theoretical one. It is benign, and only benign, for two independent
    reasons that both have to keep holding:

    1. WorkItem.Meta.ordering = ["position", "id"] is a TOTAL order
       (position ties are broken by id), so a duplicate position never
       makes display order ambiguous or nondeterministic — it just makes
       the tie-break do the work "position" alone couldn't.
    2. move_work_item() renumbers the ENTIRE destination column to a clean
       0..n-1 on every move, not just the two rows it touches — so the
       very first drag in that column, by anyone, heals the duplicate.

    Anyone narrowing move_work_item() to shift only the immediate
    neighbours instead of renumbering the whole column, or dropping the
    `id` tiebreak from WorkItem.Meta.ordering, turns this from a harmless,
    self-healing quirk into a visible board-shuffle bug — two items
    fighting for the same slot with no defined order between them. Don't
    "fix" this by locking next_position(); the cost (a lock on every
    create) buys nothing that isn't already covered above.
    """
    highest = WorkItem.objects.filter(board_id=board_id, status=status).aggregate(
        highest=Max("position")
    )["highest"]
    return 0 if highest is None else highest + 1


@transaction.atomic
def move_work_item(item: WorkItem, new_status: str, new_position: int) -> WorkItem:
    """Drop a work item into a column at a position, then renumber the
    affected columns.

    The honest guarantee this module gives is NOT "positions are always a
    contiguous 0..n-1 for a column" — that is not a standing system
    invariant, and nothing enforces it outside of a move. Deleting the
    item at position 0 out of [0, 1, 2] leaves [1, 2] with no concurrency,
    no bug, and no renumbering involved — gaps like that are EXPECTED and
    HARMLESS, not a defect to fix (this module deliberately does not
    renumber on delete; see next_position() above for why a non-zero-based
    column is still safe to append to).

    What IS guaranteed: `position` (tie-broken by `id`, see
    WorkItem.Meta.ordering) gives every column a deterministic total
    order, and THIS function renormalises the columns it touches to a
    clean 0..n-1 at the moment it runs — that renumbering is a one-time
    side effect of a move, not an invariant that holds continuously
    afterward (the next delete reopens a gap, same as always). Every item
    on the board is locked with SELECT ... FOR UPDATE. That is heavier
    than locking two columns, but a board holds tens of rows, and it buys
    real safety: two concurrent moves on the SAME board issue the
    identical `WHERE board_id = ?` predicate against the same index, so
    both transactions scan (and therefore lock) the rows in the same
    order — that shared predicate/index is what makes them serialise
    instead of deadlocking. The trailing `order_by("id")` is a filesort
    applied to rows that are already locked by then; it gives the
    renumbering a stable, deterministic order to read in, but it plays no
    part in lock acquisition and is NOT what prevents the deadlock. Moves
    on different boards lock disjoint row sets and never contend at all.
    Do not narrow this to a two-column lock on the theory that the ORDER
    BY protects it — it doesn't; any narrower filter would need its own
    argument for why it stays deadlock-free.
    """
    locked = list(
        WorkItem.objects.select_for_update()
        .filter(board_id=item.board_id)
        .order_by("id")
    )

    locked_by_pk = {c.pk: c for c in locked}
    if item.pk not in locked_by_pk:
        # `item` was fetched (unlocked) by the view before this transaction
        # took the lock. If another request deleted it in between, trusting
        # `item.status` here would use a stale, possibly-wrong old_status,
        # renumbering the wrong column, and inserting `item` into the
        # destination column would resurrect a ghost row that bulk_update
        # never writes, leaving the destination with a hole. Surface it as
        # "gone" instead.
        raise WorkItem.DoesNotExist(
            f"WorkItem {item.pk} was deleted before the move could be applied."
        )

    old_status = locked_by_pk[item.pk].status
    item.status = new_status

    def renumber(status: str) -> list[WorkItem]:
        column = [c for c in locked if c.status == status and c.pk != item.pk]
        column.sort(key=lambda c: (c.position, c.pk))

        if status == new_status:
            index = max(0, min(new_position, len(column)))
            column.insert(index, item)

        now = timezone.now()
        for index, member in enumerate(column):
            member.position = index
            member.updated_at = now
        return column

    touched = renumber(new_status)
    if old_status != new_status:
        touched += renumber(old_status)

    WorkItem.objects.bulk_update(touched, ["position", "status", "updated_at"])
    return item

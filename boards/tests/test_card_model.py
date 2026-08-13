import datetime

import pytest

from boards.models import Board, Card
from boards.services import next_position


@pytest.fixture
def board(user, project):
    return Board.objects.create(name="Test Board", created_by=user, project=project)


@pytest.mark.django_db
def test_card_defaults(board):
    card = Card.objects.create(board=board, title="Write the spec")

    assert card.status == Card.Status.TODO
    assert card.priority == Card.Priority.MEDIUM
    assert card.due_date is None
    assert card.assignee is None
    assert card.description == ""


@pytest.mark.django_db
def test_card_stringifies_to_its_title(board):
    assert str(Card.objects.create(board=board, title="Ship it")) == "Ship it"


@pytest.mark.django_db
def test_next_position_starts_at_zero(board):
    assert next_position(board.id, Card.Status.TODO) == 0


@pytest.mark.django_db
def test_next_position_appends_to_the_end_of_its_column(board):
    Card.objects.create(board=board, title="A", status=Card.Status.TODO, position=0)
    Card.objects.create(board=board, title="B", status=Card.Status.TODO, position=1)

    assert next_position(board.id, Card.Status.TODO) == 2


@pytest.mark.django_db
def test_next_position_counts_each_column_separately(board):
    Card.objects.create(board=board, title="A", status=Card.Status.TODO, position=0)
    Card.objects.create(board=board, title="B", status=Card.Status.TODO, position=1)

    assert next_position(board.id, Card.Status.DONE) == 0


@pytest.mark.django_db
def test_cards_are_ordered_by_position_within_a_column(board):
    second = Card.objects.create(board=board, title="Second", position=1)
    first = Card.objects.create(board=board, title="First", position=0)

    assert list(Card.objects.filter(status=Card.Status.TODO)) == [first, second]


@pytest.mark.django_db
def test_deleting_a_board_deletes_its_cards(board):
    Card.objects.create(board=board, title="Doomed")
    board.delete()
    assert Card.objects.count() == 0


@pytest.mark.django_db
def test_unassigning_happens_when_the_assignee_is_deleted(board, other_user):
    card = Card.objects.create(board=board, title="Orphan", assignee=other_user)
    other_user.delete()
    card.refresh_from_db()
    assert card.assignee is None


@pytest.mark.django_db
def test_due_date_can_be_set(board):
    card = Card.objects.create(
        board=board, title="Dated", due_date=datetime.date(2026, 8, 15)
    )
    assert card.due_date == datetime.date(2026, 8, 15)

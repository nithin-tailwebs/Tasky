import pytest

from boards.models import Board


@pytest.mark.django_db
def test_board_stringifies_to_its_name(user):
    board = Board.objects.create(name="Website Redesign", created_by=user)
    assert str(board) == "Website Redesign"


@pytest.mark.django_db
def test_description_is_optional(user):
    board = Board.objects.create(name="Ops", created_by=user)
    assert board.description == ""


@pytest.mark.django_db
def test_boards_are_ordered_newest_first(user):
    first = Board.objects.create(name="First", created_by=user)
    second = Board.objects.create(name="Second", created_by=user)
    assert list(Board.objects.all()) == [second, first]


@pytest.mark.django_db
def test_board_survives_its_creator_being_deleted(user):
    board = Board.objects.create(name="Orphan", created_by=user)
    user.delete()
    board.refresh_from_db()
    assert board.created_by is None

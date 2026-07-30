import datetime

import pytest

from boards.models import Board, Card


@pytest.fixture
def board(user):
    return Board.objects.create(name="Test Board", created_by=user)


@pytest.mark.django_db
def test_anonymous_callers_are_rejected(client):
    assert client.get("/api/me/tasks/").status_code == 403


@pytest.mark.django_db
def test_only_my_cards_come_back(auth_client, board, user, other_user):
    Card.objects.create(board=board, title="Mine", assignee=user)
    Card.objects.create(board=board, title="Theirs", assignee=other_user)
    Card.objects.create(board=board, title="Nobody's")

    response = auth_client.get("/api/me/tasks/")

    assert response.status_code == 200
    assert [card["title"] for card in response.json()] == ["Mine"]


@pytest.mark.django_db
def test_my_cards_span_every_board(auth_client, board, user):
    second_board = Board.objects.create(name="Second", created_by=user)
    Card.objects.create(board=board, title="From board one", assignee=user)
    Card.objects.create(board=second_board, title="From board two", assignee=user)

    response = auth_client.get("/api/me/tasks/")

    assert {card["title"] for card in response.json()} == {
        "From board one",
        "From board two",
    }


@pytest.mark.django_db
def test_soonest_due_first_with_undated_cards_last(auth_client, board, user):
    Card.objects.create(board=board, title="No date", assignee=user)
    Card.objects.create(
        board=board, title="Later", assignee=user, due_date=datetime.date(2026, 9, 1)
    )
    Card.objects.create(
        board=board, title="Sooner", assignee=user, due_date=datetime.date(2026, 8, 1)
    )

    response = auth_client.get("/api/me/tasks/")

    assert [card["title"] for card in response.json()] == ["Sooner", "Later", "No date"]


@pytest.mark.django_db
def test_undated_cards_break_ties_on_priority(auth_client, board, user):
    Card.objects.create(board=board, title="Low", assignee=user, priority=1)
    Card.objects.create(board=board, title="High", assignee=user, priority=3)

    response = auth_client.get("/api/me/tasks/")

    assert [card["title"] for card in response.json()] == ["High", "Low"]


@pytest.mark.django_db
def test_finished_cards_are_excluded(auth_client, board, user):
    Card.objects.create(board=board, title="Still going", assignee=user, status="todo")
    Card.objects.create(board=board, title="Finished", assignee=user, status="done")

    response = auth_client.get("/api/me/tasks/")

    assert [card["title"] for card in response.json()] == ["Still going"]

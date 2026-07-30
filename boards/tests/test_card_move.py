import pytest

from boards.models import Board, Card


@pytest.fixture
def board(user):
    return Board.objects.create(name="Test Board", created_by=user)


@pytest.fixture
def todo_cards(board):
    return [
        Card.objects.create(board=board, title=title, status="todo", position=index)
        for index, title in enumerate(["A", "B", "C"])
    ]


def titles_in(board, status):
    return [
        card.title
        for card in Card.objects.filter(board=board, status=status).order_by(
            "position", "id"
        )
    ]


@pytest.mark.django_db
def test_moving_a_card_up_within_its_column(auth_client, board, todo_cards):
    card_c = todo_cards[2]

    response = auth_client.post(
        f"/api/cards/{card_c.id}/move/",
        {"status": "todo", "position": 0},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert titles_in(board, "todo") == ["C", "A", "B"]


@pytest.mark.django_db
def test_moving_a_card_down_within_its_column(auth_client, board, todo_cards):
    card_a = todo_cards[0]

    auth_client.post(
        f"/api/cards/{card_a.id}/move/",
        {"status": "todo", "position": 2},
        content_type="application/json",
    )

    assert titles_in(board, "todo") == ["B", "C", "A"]


@pytest.mark.django_db
def test_moving_a_card_to_another_column(auth_client, board, todo_cards):
    card_b = todo_cards[1]

    response = auth_client.post(
        f"/api/cards/{card_b.id}/move/",
        {"status": "in_progress", "position": 0},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"
    assert titles_in(board, "todo") == ["A", "C"]
    assert titles_in(board, "in_progress") == ["B"]


@pytest.mark.django_db
def test_the_source_column_closes_its_gap(auth_client, board, todo_cards):
    auth_client.post(
        f"/api/cards/{todo_cards[0].id}/move/",
        {"status": "done", "position": 0},
        content_type="application/json",
    )

    remaining = Card.objects.filter(board=board, status="todo").order_by("position")
    assert [card.position for card in remaining] == [0, 1]


@pytest.mark.django_db
def test_dropping_into_the_middle_of_a_populated_column(auth_client, board, todo_cards):
    Card.objects.create(board=board, title="X", status="done", position=0)
    Card.objects.create(board=board, title="Y", status="done", position=1)

    auth_client.post(
        f"/api/cards/{todo_cards[0].id}/move/",
        {"status": "done", "position": 1},
        content_type="application/json",
    )

    assert titles_in(board, "done") == ["X", "A", "Y"]


@pytest.mark.django_db
def test_an_oversized_position_lands_at_the_end(auth_client, board, todo_cards):
    auth_client.post(
        f"/api/cards/{todo_cards[0].id}/move/",
        {"status": "todo", "position": 999},
        content_type="application/json",
    )

    assert titles_in(board, "todo") == ["B", "C", "A"]


@pytest.mark.django_db
def test_positions_stay_contiguous_from_zero(auth_client, board, todo_cards):
    auth_client.post(
        f"/api/cards/{todo_cards[1].id}/move/",
        {"status": "todo", "position": 0},
        content_type="application/json",
    )

    positions = list(
        Card.objects.filter(board=board, status="todo")
        .order_by("position")
        .values_list("position", flat=True)
    )
    assert positions == [0, 1, 2]


@pytest.mark.django_db
def test_a_move_never_touches_another_board(auth_client, board, todo_cards, user):
    other_board = Board.objects.create(name="Elsewhere", created_by=user)
    untouched = Card.objects.create(
        board=other_board, title="Untouched", status="todo", position=7
    )

    auth_client.post(
        f"/api/cards/{todo_cards[0].id}/move/",
        {"status": "todo", "position": 2},
        content_type="application/json",
    )

    untouched.refresh_from_db()
    assert untouched.position == 7


@pytest.mark.django_db
def test_an_unknown_status_is_rejected(auth_client, todo_cards):
    response = auth_client.post(
        f"/api/cards/{todo_cards[0].id}/move/",
        {"status": "archived", "position": 0},
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_a_negative_position_is_rejected(auth_client, todo_cards):
    response = auth_client.post(
        f"/api/cards/{todo_cards[0].id}/move/",
        {"status": "todo", "position": -1},
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_anonymous_callers_are_rejected(client, todo_cards):
    response = client.post(
        f"/api/cards/{todo_cards[0].id}/move/",
        {"status": "done", "position": 0},
        content_type="application/json",
    )
    assert response.status_code == 403

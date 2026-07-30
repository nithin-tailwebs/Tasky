import pytest

from boards.models import Board, Card
from boards.services import move_card
from boards.views import CardViewSet


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
    original_updated_at = card_c.updated_at

    response = auth_client.post(
        f"/api/cards/{card_c.id}/move/",
        {"status": "todo", "position": 0},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert titles_in(board, "todo") == ["C", "A", "B"]

    card_c.refresh_from_db()
    assert card_c.updated_at > original_updated_at


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

    card_b.refresh_from_db()
    assert card_b.position == 0


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
def test_an_unknown_status_is_rejected(auth_client, board, todo_cards):
    response = auth_client.post(
        f"/api/cards/{todo_cards[0].id}/move/",
        {"status": "archived", "position": 0},
        content_type="application/json",
    )
    assert response.status_code == 400

    # A 400 must mean nothing was written, not just that the response looks
    # right — check the rows directly rather than trusting the status code alone.
    unchanged = list(
        Card.objects.filter(board=board, status="todo")
        .order_by("position")
        .values_list("title", "position")
    )
    assert unchanged == [("A", 0), ("B", 1), ("C", 2)]


@pytest.mark.django_db
def test_a_negative_position_is_rejected(auth_client, board, todo_cards):
    response = auth_client.post(
        f"/api/cards/{todo_cards[0].id}/move/",
        {"status": "todo", "position": -1},
        content_type="application/json",
    )
    assert response.status_code == 400

    unchanged = list(
        Card.objects.filter(board=board, status="todo")
        .order_by("position")
        .values_list("title", "position")
    )
    assert unchanged == [("A", 0), ("B", 1), ("C", 2)]


@pytest.mark.django_db
def test_anonymous_callers_are_rejected(client, board, todo_cards):
    response = client.post(
        f"/api/cards/{todo_cards[0].id}/move/",
        {"status": "done", "position": 0},
        content_type="application/json",
    )
    assert response.status_code == 403

    unchanged = list(
        Card.objects.filter(board=board, status="todo")
        .order_by("position")
        .values_list("title", "position")
    )
    assert unchanged == [("A", 0), ("B", 1), ("C", 2)]
    assert not Card.objects.filter(board=board, status="done").exists()


@pytest.mark.django_db
def test_move_card_raises_when_the_row_was_deleted_after_it_was_fetched(
    board, todo_cards
):
    """Direct service-level test of the Finding-1 race: the view's get_object()
    is unlocked, so by the time move_card() takes its row lock, another request
    may already have deleted the card. old_status must never be trusted from the
    stale in-memory instance, and the vanished row must not be reinserted as a
    ghost that shifts every real card in the destination column."""
    card = todo_cards[0]
    Card.objects.filter(pk=card.pk).delete()

    with pytest.raises(Card.DoesNotExist):
        move_card(card, "done", 0)


@pytest.mark.django_db
def test_moving_a_card_deleted_after_it_was_fetched_returns_404(
    auth_client, board, todo_cards, monkeypatch
):
    """Same race, exercised through the HTTP endpoint. get_object() is patched
    to return a stale Card instance for a row that has since been deleted —
    standing in for a second request winning the race between this request's
    get_object() and its row lock. The endpoint must surface this as 404 (not
    500), and it must not touch any other card on the board."""
    card = todo_cards[0]
    Card.objects.filter(pk=card.pk).delete()
    monkeypatch.setattr(CardViewSet, "get_object", lambda self: card)

    response = auth_client.post(
        f"/api/cards/{card.id}/move/",
        {"status": "done", "position": 0},
        content_type="application/json",
    )

    assert response.status_code == 404
    remaining = list(
        Card.objects.filter(board=board, status="todo")
        .order_by("position")
        .values_list("title", "position")
    )
    assert remaining == [("B", 1), ("C", 2)]

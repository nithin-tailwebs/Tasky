import pytest

from boards.models import Board, Card


@pytest.fixture
def board(user):
    return Board.objects.create(name="Test Board", created_by=user)


@pytest.mark.django_db
def test_anonymous_callers_are_rejected(client, board):
    assert client.get(f"/api/boards/{board.id}/cards/").status_code == 403


@pytest.mark.django_db
def test_listing_a_boards_cards(auth_client, board, user):
    Card.objects.create(board=board, title="First", position=0)
    Card.objects.create(board=board, title="Second", position=1)
    other_board = Board.objects.create(name="Elsewhere", created_by=user)
    Card.objects.create(board=other_board, title="Not mine")

    response = auth_client.get(f"/api/boards/{board.id}/cards/")

    assert response.status_code == 200
    assert [card["title"] for card in response.json()] == ["First", "Second"]


@pytest.mark.django_db
def test_creating_a_card_sets_creator_and_appends_it(auth_client, board, user):
    Card.objects.create(board=board, title="Existing", status="todo", position=0)

    response = auth_client.post(
        "/api/cards/",
        {"board": board.id, "title": "New card"},
        content_type="application/json",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["position"] == 1
    assert body["status"] == "todo"
    assert body["priority"] == 2
    assert body["priority_label"] == "Medium"
    assert Card.objects.get(title="New card").created_by == user


@pytest.mark.django_db
def test_creating_a_card_with_an_assignee_and_a_due_date(auth_client, board, other_user):
    response = auth_client.post(
        "/api/cards/",
        {
            "board": board.id,
            "title": "Assigned",
            "assignee": other_user.id,
            "due_date": "2026-08-15",
            "priority": 3,
        },
        content_type="application/json",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["assignee_detail"]["username"] == "bob"
    assert body["due_date"] == "2026-08-15"
    assert body["priority_label"] == "High"


@pytest.mark.django_db
def test_editing_a_card(auth_client, board):
    card = Card.objects.create(board=board, title="Before")

    response = auth_client.patch(
        f"/api/cards/{card.id}/",
        {"title": "After", "description": "Now with detail"},
        content_type="application/json",
    )

    assert response.status_code == 200
    card.refresh_from_db()
    assert card.title == "After"
    assert card.description == "Now with detail"


@pytest.mark.django_db
def test_unassigning_a_card(auth_client, board, other_user):
    card = Card.objects.create(board=board, title="Assigned", assignee=other_user)

    response = auth_client.patch(
        f"/api/cards/{card.id}/",
        {"assignee": None},
        content_type="application/json",
    )

    assert response.status_code == 200
    card.refresh_from_db()
    assert card.assignee is None


@pytest.mark.django_db
def test_listing_all_cards_is_unscoped_by_board(auth_client, board, user):
    other_board = Board.objects.create(name="Elsewhere", created_by=user)
    Card.objects.create(board=board, title="Mine", position=0)
    Card.objects.create(board=other_board, title="Also visible", position=0)

    response = auth_client.get("/api/cards/")

    assert response.status_code == 200
    assert {card["title"] for card in response.json()} == {"Mine", "Also visible"}


@pytest.mark.django_db
def test_retrieving_a_single_card(auth_client, board):
    card = Card.objects.create(board=board, title="One card", position=0)

    response = auth_client.get(f"/api/cards/{card.id}/")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == card.id
    assert body["title"] == "One card"


@pytest.mark.django_db
def test_deleting_a_card(auth_client, board):
    card = Card.objects.create(board=board, title="Doomed")
    assert auth_client.delete(f"/api/cards/{card.id}/").status_code == 204
    assert not Card.objects.filter(id=card.id).exists()


@pytest.mark.django_db
def test_position_cannot_be_set_directly(auth_client, board):
    response = auth_client.post(
        "/api/cards/",
        {"board": board.id, "title": "Sneaky", "position": 99},
        content_type="application/json",
    )

    assert response.status_code == 201
    assert response.json()["position"] == 0


@pytest.mark.django_db
def test_title_is_required(auth_client, board):
    response = auth_client.post(
        "/api/cards/", {"board": board.id}, content_type="application/json"
    )
    assert response.status_code == 400
    assert "title" in response.json()


@pytest.mark.django_db
def test_patching_status_is_rejected(auth_client, board):
    card = Card.objects.create(board=board, title="Untouched", status="todo")

    response = auth_client.patch(
        f"/api/cards/{card.id}/",
        {"status": "done"},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "status" in response.json()
    card.refresh_from_db()
    assert card.status == "todo"


@pytest.mark.django_db
def test_patching_with_status_unchanged_still_updates_other_fields(auth_client, board):
    """A UI that PATCHes back the full set of fields it's holding — status
    included, but unchanged — must not have a genuine edit (title, here)
    rejected just because "status" was present in the body. Only an actual
    status CHANGE is rejected; round 2 fix for the round-1 regression."""
    card = Card.objects.create(board=board, title="Before", status="todo")

    response = auth_client.patch(
        f"/api/cards/{card.id}/",
        {"status": "todo", "title": "After"},
        content_type="application/json",
    )

    assert response.status_code == 200
    card.refresh_from_db()
    assert card.title == "After"
    assert card.status == "todo"


@pytest.mark.django_db
def test_patching_title_still_works(auth_client, board):
    card = Card.objects.create(board=board, title="Before", status="todo")

    response = auth_client.patch(
        f"/api/cards/{card.id}/",
        {"title": "After"},
        content_type="application/json",
    )

    assert response.status_code == 200
    card.refresh_from_db()
    assert card.title == "After"
    assert card.status == "todo"


@pytest.mark.django_db
def test_patching_board_is_rejected(auth_client, board, user):
    other_board = Board.objects.create(name="Elsewhere", created_by=user)
    card = Card.objects.create(board=board, title="Untouched", status="todo")

    response = auth_client.patch(
        f"/api/cards/{card.id}/",
        {"board": other_board.id},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "board" in response.json()
    card.refresh_from_db()
    assert card.board_id == board.id


@pytest.mark.django_db
def test_patching_with_board_unchanged_still_updates_other_fields(auth_client, board):
    """Same protection as status: a PATCH that echoes back the card's
    current, unchanged board alongside a genuine edit (title, here) must
    not be rejected just because "board" was present in the body."""
    card = Card.objects.create(board=board, title="Before", status="todo")

    response = auth_client.patch(
        f"/api/cards/{card.id}/",
        {"board": board.id, "title": "After"},
        content_type="application/json",
    )

    assert response.status_code == 200
    card.refresh_from_db()
    assert card.title == "After"
    assert card.board_id == board.id


@pytest.mark.django_db
def test_creating_a_card_with_an_explicit_status_still_works(auth_client, board):
    response = auth_client.post(
        "/api/cards/",
        {"board": board.id, "title": "Started already", "status": "in_progress"},
        content_type="application/json",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "in_progress"
    assert body["position"] == 0
    assert Card.objects.get(title="Started already").status == "in_progress"

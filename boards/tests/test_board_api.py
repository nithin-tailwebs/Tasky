import pytest

from boards.models import Board


@pytest.mark.django_db
def test_anonymous_callers_are_rejected(client):
    assert client.get("/api/boards/").status_code == 403


@pytest.mark.django_db
def test_listing_returns_every_board(auth_client, user, other_user):
    Board.objects.create(name="Mine", created_by=user)
    Board.objects.create(name="Theirs", created_by=other_user)

    response = auth_client.get("/api/boards/")

    assert response.status_code == 200
    names = {board["name"] for board in response.json()}
    assert names == {"Mine", "Theirs"}


@pytest.mark.django_db
def test_creating_a_board_records_the_creator(auth_client, user):
    response = auth_client.post(
        "/api/boards/",
        {"name": "Q3 Launch", "description": "Everything for the launch"},
        content_type="application/json",
    )

    assert response.status_code == 201
    assert response.json()["created_by"]["username"] == "alice"
    assert Board.objects.get(name="Q3 Launch").created_by == user


@pytest.mark.django_db
def test_created_by_cannot_be_forged(auth_client, other_user):
    response = auth_client.post(
        "/api/boards/",
        {"name": "Spoofed", "created_by": other_user.id},
        content_type="application/json",
    )

    assert response.status_code == 201
    assert Board.objects.get(name="Spoofed").created_by.username == "alice"


@pytest.mark.django_db
def test_a_board_can_be_renamed(auth_client, user):
    board = Board.objects.create(name="Old Name", created_by=user)

    response = auth_client.patch(
        f"/api/boards/{board.id}/",
        {"name": "New Name"},
        content_type="application/json",
    )

    assert response.status_code == 200
    board.refresh_from_db()
    assert board.name == "New Name"


@pytest.mark.django_db
def test_a_board_can_be_deleted(auth_client, user):
    board = Board.objects.create(name="Doomed", created_by=user)

    assert auth_client.delete(f"/api/boards/{board.id}/").status_code == 204
    assert not Board.objects.filter(id=board.id).exists()


@pytest.mark.django_db
def test_name_is_required(auth_client):
    response = auth_client.post(
        "/api/boards/", {"description": "no name"}, content_type="application/json"
    )
    assert response.status_code == 400
    assert "name" in response.json()

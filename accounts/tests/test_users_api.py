import pytest


@pytest.mark.django_db
def test_anonymous_callers_are_rejected(client):
    assert client.get("/api/users/").status_code == 403


@pytest.mark.django_db
def test_listing_users_for_the_assignee_dropdown(auth_client, user, other_user):
    response = auth_client.get("/api/users/")

    assert response.status_code == 200
    assert {row["username"] for row in response.json()} == {"alice", "bob"}
    assert set(response.json()[0]) == {"id", "username", "display_name"}


@pytest.mark.django_db
def test_deactivated_users_are_hidden(auth_client, user, other_user):
    other_user.is_active = False
    other_user.save()

    response = auth_client.get("/api/users/")

    assert [row["username"] for row in response.json()] == ["alice"]


@pytest.mark.django_db
def test_no_password_hash_is_ever_exposed(auth_client, user):
    body = auth_client.get("/api/users/").json()
    assert "password" not in body[0]

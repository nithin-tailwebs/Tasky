import pytest
from django.test import Client

from boards.models import Board


@pytest.fixture
def csrf_client():
    """A Client with CSRF enforcement turned ON.

    Every other test in this suite uses the default `client` fixture
    (enforce_csrf_checks=False) or force_login, so nothing else in the
    suite actually proves the CSRF boundary holds — only that the cookie
    gets issued. Same-origin session auth relies on this middleware being
    the thing standing between a signed-in cookie and a forged POST from
    another site, so it needs its own direct test.
    """
    return Client(enforce_csrf_checks=True)


@pytest.fixture
def board(user, project):
    return Board.objects.create(name="Test Board", created_by=user, project=project)


@pytest.mark.django_db
def test_write_without_csrf_token_is_rejected(csrf_client, user, board):
    csrf_client.force_login(user)

    response = csrf_client.post(
        "/api/work-items/",
        {"board": board.id, "title": "Should not be created"},
        content_type="application/json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_write_with_valid_csrf_token_succeeds(csrf_client, user, board):
    csrf_client.force_login(user)

    csrf_response = csrf_client.get("/api/auth/csrf/")
    assert csrf_response.status_code == 204
    token = csrf_response.cookies["csrftoken"].value

    response = csrf_client.post(
        "/api/work-items/",
        {"board": board.id, "title": "Created with a valid token"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )

    assert response.status_code == 201

import pytest


@pytest.mark.django_db
def test_login_succeeds_with_correct_password(client, user):
    response = client.post(
        "/api/auth/login/",
        {"username": "alice", "password": "pw-alice-12345"},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["username"] == "alice"
    assert response.json()["display_name"] == "Alice"

    # The only untested link between LoginView and a future React client:
    # prove the session cookie LoginView set actually authenticates a
    # following request on the same client, not just that the response
    # body looked right.
    me_response = client.get("/api/auth/me/")
    assert me_response.status_code == 200
    assert me_response.json()["username"] == "alice"


@pytest.mark.django_db
def test_login_fails_with_wrong_password(client, user):
    response = client.post(
        "/api/auth/login/",
        {"username": "alice", "password": "wrong-password"},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "password" in response.json()["detail"].lower()


@pytest.mark.django_db
def test_login_does_not_reveal_whether_the_username_exists(client, user):
    unknown = client.post(
        "/api/auth/login/",
        {"username": "nobody", "password": "wrong-password"},
        content_type="application/json",
    )
    known = client.post(
        "/api/auth/login/",
        {"username": "alice", "password": "wrong-password"},
        content_type="application/json",
    )
    assert unknown.json() == known.json()


@pytest.mark.django_db
def test_me_returns_the_signed_in_user(auth_client):
    response = auth_client.get("/api/auth/me/")
    assert response.status_code == 200
    assert response.json()["username"] == "alice"


@pytest.mark.django_db
def test_me_rejects_anonymous_callers(client):
    response = client.get("/api/auth/me/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_logout_ends_the_session(auth_client):
    assert auth_client.post("/api/auth/logout/").status_code == 204
    assert auth_client.get("/api/auth/me/").status_code == 403


@pytest.mark.django_db
def test_csrf_endpoint_sets_the_cookie(client):
    response = client.get("/api/auth/csrf/")
    assert response.status_code == 204
    assert "csrftoken" in response.cookies

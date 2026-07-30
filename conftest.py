import pytest
from django.contrib.auth import get_user_model


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(
        username="alice", password="pw-alice-12345", first_name="Alice"
    )


@pytest.fixture
def other_user(db):
    return get_user_model().objects.create_user(
        username="bob", password="pw-bob-12345", first_name="Bob"
    )


@pytest.fixture
def auth_client(client, user):
    client.force_login(user)
    return client

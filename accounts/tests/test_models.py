import pytest
from django.contrib.auth import get_user_model


def test_user_model_is_the_custom_one():
    assert get_user_model()._meta.label == "accounts.User"


@pytest.mark.django_db
def test_display_name_prefers_full_name():
    user = get_user_model().objects.create_user(
        username="carol", password="pw-carol-12345",
        first_name="Carol", last_name="Danvers",
    )
    assert user.display_name == "Carol Danvers"


@pytest.mark.django_db
def test_display_name_falls_back_to_username():
    user = get_user_model().objects.create_user(
        username="dave", password="pw-dave-12345"
    )
    assert user.display_name == "dave"


@pytest.mark.django_db
def test_admin_login_page_loads(client):
    response = client.get("/admin/login/")
    assert response.status_code == 200

import pytest

from projects.models import Invitation, Project, ProjectMembership


@pytest.fixture
def owned_project(user, other_user):
    project = Project.objects.create(key="TASKY", name="Tasky Redesign")
    ProjectMembership.objects.create(project=project, user=user, role="owner")
    ProjectMembership.objects.create(project=project, user=other_user, role="admin")
    return project


@pytest.mark.django_db
def test_owner_can_transfer_to_an_admin(auth_client, owned_project, user, other_user):
    response = auth_client.post(f"/api/projects/{owned_project.id}/transfer-ownership/",
                                 {"user_id": other_user.id}, content_type="application/json")

    assert response.status_code == 204
    assert ProjectMembership.objects.get(project=owned_project, user=user).role == "admin"
    assert ProjectMembership.objects.get(project=owned_project, user=other_user).role == "owner"


@pytest.mark.django_db
def test_cannot_transfer_to_a_plain_member(auth_client, owned_project, user):
    from django.contrib.auth import get_user_model

    plain = get_user_model().objects.create_user(username="carol", password="pw-carol-12345")
    ProjectMembership.objects.create(project=owned_project, user=plain, role="member")

    response = auth_client.post(f"/api/projects/{owned_project.id}/transfer-ownership/",
                                 {"user_id": plain.id}, content_type="application/json")

    assert response.status_code == 400
    assert ProjectMembership.objects.get(project=owned_project, user=user).role == "owner"


@pytest.mark.django_db
def test_admin_cannot_transfer_ownership(auth_client, other_user, owned_project):
    auth_client.logout()
    auth_client.force_login(other_user)

    response = auth_client.post(f"/api/projects/{owned_project.id}/transfer-ownership/",
                                 {"user_id": other_user.id}, content_type="application/json")

    assert response.status_code == 403


@pytest.mark.django_db
def test_owner_can_invite_a_non_member(auth_client, owned_project):
    from django.contrib.auth import get_user_model

    outsider = get_user_model().objects.create_user(username="carol", password="pw-carol-12345")

    response = auth_client.post(f"/api/projects/{owned_project.id}/invite/",
                                 {"user_id": outsider.id}, content_type="application/json")

    assert response.status_code == 201
    invitation = Invitation.objects.get(project=owned_project, invited_user=outsider)
    assert invitation.status == Invitation.Status.PENDING


@pytest.mark.django_db
def test_admin_can_also_invite(auth_client, other_user, owned_project):
    from django.contrib.auth import get_user_model

    outsider = get_user_model().objects.create_user(username="carol", password="pw-carol-12345")
    auth_client.logout()
    auth_client.force_login(other_user)  # admin

    response = auth_client.post(f"/api/projects/{owned_project.id}/invite/",
                                 {"user_id": outsider.id}, content_type="application/json")

    assert response.status_code == 201


@pytest.mark.django_db
def test_member_cannot_invite(auth_client, owned_project):
    from django.contrib.auth import get_user_model

    plain = get_user_model().objects.create_user(username="carol", password="pw-carol-12345")
    ProjectMembership.objects.create(project=owned_project, user=plain, role="member")
    outsider = get_user_model().objects.create_user(username="dave", password="pw-dave-12345")

    auth_client.logout()
    auth_client.force_login(plain)

    response = auth_client.post(f"/api/projects/{owned_project.id}/invite/",
                                 {"user_id": outsider.id}, content_type="application/json")

    assert response.status_code == 403


@pytest.mark.django_db
def test_inviting_an_existing_member_is_rejected(auth_client, owned_project, other_user):
    response = auth_client.post(f"/api/projects/{owned_project.id}/invite/",
                                 {"user_id": other_user.id}, content_type="application/json")

    assert response.status_code == 400


@pytest.mark.django_db
def test_inviting_someone_twice_is_rejected(auth_client, owned_project):
    from django.contrib.auth import get_user_model

    outsider = get_user_model().objects.create_user(username="carol", password="pw-carol-12345")
    auth_client.post(f"/api/projects/{owned_project.id}/invite/",
                      {"user_id": outsider.id}, content_type="application/json")

    response = auth_client.post(f"/api/projects/{owned_project.id}/invite/",
                                 {"user_id": outsider.id}, content_type="application/json")

    assert response.status_code == 400

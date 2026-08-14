import pytest

from projects.models import Project, ProjectMembership


@pytest.fixture
def project_with_roles(user, other_user):
    """user=owner, other_user=admin, a third member as plain member."""
    from django.contrib.auth import get_user_model

    third = get_user_model().objects.create_user(username="carol", password="pw-carol-12345")
    project = Project.objects.create(key="TASKY", name="Tasky Redesign")
    ProjectMembership.objects.create(project=project, user=user, role="owner")
    ProjectMembership.objects.create(project=project, user=other_user, role="admin")
    ProjectMembership.objects.create(project=project, user=third, role="member")
    return project, third


@pytest.mark.django_db
def test_listing_members_is_sorted_owner_first(auth_client, project_with_roles):
    project, _ = project_with_roles
    response = auth_client.get(f"/api/projects/{project.id}/members/")

    assert response.status_code == 200
    roles = [m["role"] for m in response.json()]
    assert roles == ["owner", "admin", "member"]


@pytest.mark.django_db
def test_owner_can_remove_an_admin(auth_client, project_with_roles, other_user):
    project, _ = project_with_roles
    response = auth_client.delete(f"/api/projects/{project.id}/members/{other_user.id}/")

    assert response.status_code == 204
    assert not ProjectMembership.objects.filter(project=project, user=other_user).exists()


@pytest.mark.django_db
def test_admin_cannot_remove_another_admin(auth_client, other_user, project_with_roles):
    from django.contrib.auth import get_user_model

    project, _ = project_with_roles
    second_admin = get_user_model().objects.create_user(username="dave", password="pw-dave-12345")
    ProjectMembership.objects.create(project=project, user=second_admin, role="admin")

    auth_client.logout()
    auth_client.force_login(other_user)  # other_user is admin here

    response = auth_client.delete(f"/api/projects/{project.id}/members/{second_admin.id}/")

    assert response.status_code == 403
    assert ProjectMembership.objects.filter(project=project, user=second_admin).exists()


@pytest.mark.django_db
def test_admin_can_remove_a_member(auth_client, other_user, project_with_roles):
    project, third = project_with_roles
    auth_client.logout()
    auth_client.force_login(other_user)  # other_user is admin here

    response = auth_client.delete(f"/api/projects/{project.id}/members/{third.id}/")

    assert response.status_code == 204
    assert not ProjectMembership.objects.filter(project=project, user=third).exists()


@pytest.mark.django_db
def test_owner_cannot_leave_without_transferring_first(auth_client, project_with_roles, user):
    project, _ = project_with_roles
    response = auth_client.delete(f"/api/projects/{project.id}/members/{user.id}/")

    assert response.status_code == 400
    assert ProjectMembership.objects.filter(project=project, user=user).exists()


@pytest.mark.django_db
def test_admin_can_remove_themself_to_leave(auth_client, other_user, project_with_roles):
    project, _ = project_with_roles
    auth_client.logout()
    auth_client.force_login(other_user)  # admin

    response = auth_client.delete(f"/api/projects/{project.id}/members/{other_user.id}/")

    assert response.status_code == 204
    assert not ProjectMembership.objects.filter(project=project, user=other_user).exists()


@pytest.mark.django_db
def test_member_can_remove_themself_to_leave(auth_client, project_with_roles):
    project, third = project_with_roles
    auth_client.logout()
    auth_client.force_login(third)  # plain member

    response = auth_client.delete(f"/api/projects/{project.id}/members/{third.id}/")

    assert response.status_code == 204
    assert not ProjectMembership.objects.filter(project=project, user=third).exists()


@pytest.mark.django_db
def test_owner_can_change_a_members_role(auth_client, project_with_roles):
    project, third = project_with_roles
    response = auth_client.post(
        f"/api/projects/{project.id}/members/{third.id}/role/",
        {"role": "admin"},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert ProjectMembership.objects.get(project=project, user=third).role == "admin"


@pytest.mark.django_db
def test_admin_cannot_change_roles(auth_client, other_user, project_with_roles):
    project, third = project_with_roles
    auth_client.logout()
    auth_client.force_login(other_user)  # admin

    response = auth_client.post(
        f"/api/projects/{project.id}/members/{third.id}/role/",
        {"role": "admin"},
        content_type="application/json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_a_non_numeric_user_id_in_the_url_is_404_not_500(auth_client, project_with_roles):
    project, _ = project_with_roles
    response = auth_client.delete(f"/api/projects/{project.id}/members/not-a-number/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_the_owners_role_cannot_be_changed_here(auth_client, project_with_roles, user, other_user):
    project, _ = project_with_roles
    # other_user (admin) tries to demote... but only owner can change roles at
    # all, so switch to owner (`user`) attempting to change the OWNER's own role.
    response = auth_client.post(
        f"/api/projects/{project.id}/members/{user.id}/role/",
        {"role": "member"},
        content_type="application/json",
    )

    assert response.status_code == 403

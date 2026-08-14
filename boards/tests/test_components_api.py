import pytest

from boards.models import Board, Component, WorkItem


@pytest.fixture
def board(user, project):
    return Board.objects.create(name="Test Board", created_by=user, project=project)


@pytest.mark.django_db
def test_anonymous_callers_are_rejected(client, project):
    assert client.get(f"/api/projects/{project.id}/components/").status_code == 403


@pytest.mark.django_db
def test_owner_can_create_a_component(auth_client, project):
    response = auth_client.post(
        f"/api/projects/{project.id}/components/", {"name": "Frontend"}, content_type="application/json"
    )
    assert response.status_code == 201
    assert Component.objects.get(project=project, name="Frontend")


@pytest.mark.django_db
def test_member_cannot_create_a_component(auth_client, other_user, project):
    from projects.models import ProjectMembership

    ProjectMembership.objects.filter(project=project, user__username="alice").update(role="member")
    response = auth_client.post(
        f"/api/projects/{project.id}/components/", {"name": "Backend"}, content_type="application/json"
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_duplicate_component_name_in_the_same_project_is_rejected(auth_client, project):
    Component.objects.create(project=project, name="Frontend")
    response = auth_client.post(
        f"/api/projects/{project.id}/components/", {"name": "Frontend"}, content_type="application/json"
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_owner_can_rename_a_component(auth_client, project):
    component = Component.objects.create(project=project, name="Old name")
    response = auth_client.patch(
        f"/api/projects/{project.id}/components/{component.id}/", {"name": "New name"}, content_type="application/json"
    )
    assert response.status_code == 200
    component.refresh_from_db()
    assert component.name == "New name"


@pytest.mark.django_db
def test_owner_can_delete_a_component(auth_client, project):
    component = Component.objects.create(project=project, name="Doomed")
    assert auth_client.delete(f"/api/projects/{project.id}/components/{component.id}/").status_code == 204
    assert not Component.objects.filter(id=component.id).exists()


@pytest.mark.django_db
def test_deleting_a_component_clears_it_from_work_items_without_deleting_them(auth_client, board, project):
    component = Component.objects.create(project=project, name="Frontend")
    item = WorkItem.objects.create(board=board, title="Has a component")
    item.components.add(component)

    auth_client.delete(f"/api/projects/{project.id}/components/{component.id}/")

    item.refresh_from_db()
    assert WorkItem.objects.filter(id=item.id).exists()
    assert component.id not in item.components.values_list("id", flat=True)


@pytest.mark.django_db
def test_any_member_can_apply_an_existing_component_to_a_work_item(auth_client, board, project):
    component = Component.objects.create(project=project, name="Frontend")
    item = WorkItem.objects.create(board=board, title="Needs tagging")

    response = auth_client.patch(
        f"/api/work-items/{item.id}/", {"components": [component.id]}, content_type="application/json"
    )

    assert response.status_code == 200
    assert response.json()["components_detail"][0]["name"] == "Frontend"


@pytest.mark.django_db
def test_a_component_from_another_project_cannot_be_applied(auth_client, board, other_user):
    from projects.models import Project, ProjectMembership

    foreign_project = Project.objects.create(key="FOREIGN", name="Not Yours")
    ProjectMembership.objects.create(project=foreign_project, user=other_user, role="owner")
    foreign_component = Component.objects.create(project=foreign_project, name="Not applicable")
    item = WorkItem.objects.create(board=board, title="Item")

    response = auth_client.patch(
        f"/api/work-items/{item.id}/", {"components": [foreign_component.id]}, content_type="application/json"
    )

    assert response.status_code == 400
    assert "components" in response.json()

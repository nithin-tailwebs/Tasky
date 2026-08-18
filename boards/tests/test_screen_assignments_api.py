import pytest

from boards.models import ProjectScreenAssignment, Screen


@pytest.mark.django_db
def test_anonymous_callers_are_rejected(client, project):
    assert client.get(f"/api/projects/{project.id}/screen-assignments/").status_code == 403


@pytest.mark.django_db
def test_a_non_member_cannot_view_assignments(auth_client, other_user):
    from projects.models import Project, ProjectMembership

    foreign = Project.objects.create(key="FOREIGN", name="Not Yours")
    ProjectMembership.objects.create(project=foreign, user=other_user, role="owner")

    assert auth_client.get(f"/api/projects/{foreign.id}/screen-assignments/").status_code == 403


@pytest.mark.django_db
def test_a_fresh_project_has_no_assignments(auth_client, project):
    response = auth_client.get(f"/api/projects/{project.id}/screen-assignments/")
    assert response.status_code == 200
    assert response.json() == {
        "epic": None, "story": None, "task": None, "bug": None, "subtask": None,
    }


@pytest.mark.django_db
def test_owner_can_assign_a_screen(auth_client, project):
    screen = Screen.objects.create(name="Bug screen")
    response = auth_client.put(
        f"/api/projects/{project.id}/screen-assignments/", {"task": screen.id}, content_type="application/json"
    )
    assert response.status_code == 200
    assert response.json()["task"] == screen.id
    assert ProjectScreenAssignment.objects.get(project=project, item_type="task").screen_id == screen.id


@pytest.mark.django_db
def test_a_plain_member_cannot_assign_a_screen(auth_client, project):
    from projects.models import ProjectMembership

    ProjectMembership.objects.filter(project=project, user__username="alice").update(role="member")
    screen = Screen.objects.create(name="Bug screen")
    response = auth_client.put(
        f"/api/projects/{project.id}/screen-assignments/", {"task": screen.id}, content_type="application/json"
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_setting_an_assignment_to_null_clears_it(auth_client, project):
    screen = Screen.objects.create(name="Bug screen")
    ProjectScreenAssignment.objects.create(project=project, item_type="task", screen=screen)

    response = auth_client.put(
        f"/api/projects/{project.id}/screen-assignments/", {"task": None}, content_type="application/json"
    )
    assert response.status_code == 200
    assert response.json()["task"] is None
    assert not ProjectScreenAssignment.objects.filter(project=project, item_type="task").exists()


@pytest.mark.django_db
def test_reassigning_an_item_type_replaces_the_old_screen(auth_client, project):
    screen_a = Screen.objects.create(name="A")
    screen_b = Screen.objects.create(name="B")
    ProjectScreenAssignment.objects.create(project=project, item_type="task", screen=screen_a)

    response = auth_client.put(
        f"/api/projects/{project.id}/screen-assignments/", {"task": screen_b.id}, content_type="application/json"
    )
    assert response.status_code == 200
    assert ProjectScreenAssignment.objects.filter(project=project, item_type="task").count() == 1
    assert ProjectScreenAssignment.objects.get(project=project, item_type="task").screen_id == screen_b.id


@pytest.mark.django_db
def test_an_invalid_item_type_key_is_rejected(auth_client, project):
    screen = Screen.objects.create(name="Bug screen")
    response = auth_client.put(
        f"/api/projects/{project.id}/screen-assignments/",
        {"not_a_type": screen.id},
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_assigning_a_nonexistent_screen_is_rejected(auth_client, project):
    response = auth_client.put(
        f"/api/projects/{project.id}/screen-assignments/", {"task": 999999}, content_type="application/json"
    )
    assert response.status_code == 400
    assert not ProjectScreenAssignment.objects.filter(project=project, item_type="task").exists()


@pytest.mark.django_db
def test_assignments_are_scoped_per_project(auth_client, project, user):
    from projects.models import Project, ProjectMembership

    other_project = Project.objects.create(key="OTHER", name="Elsewhere")
    ProjectMembership.objects.create(project=other_project, user=user, role="owner")
    screen = Screen.objects.create(name="Shared screen")

    auth_client.put(f"/api/projects/{project.id}/screen-assignments/", {"task": screen.id}, content_type="application/json")
    response = auth_client.get(f"/api/projects/{other_project.id}/screen-assignments/")

    assert response.json()["task"] is None


@pytest.mark.django_db
def test_deleting_a_screen_still_assigned_somewhere_is_rejected(auth_client, project):
    """The real guard on ScreenViewSet.perform_destroy, now that
    ProjectScreenAssignment exists — Task 2 left this endpoint unguarded
    since it was introduced before this model was."""
    screen = Screen.objects.create(name="In use")
    ProjectScreenAssignment.objects.create(project=project, item_type="task", screen=screen)

    response = auth_client.delete(f"/api/screens/{screen.id}/")
    assert response.status_code == 400
    assert Screen.objects.filter(id=screen.id).exists()


@pytest.mark.django_db
def test_put_with_non_dict_body_is_rejected(auth_client, project):
    response = auth_client.put(
        f"/api/projects/{project.id}/screen-assignments/",
        [1, 2, 3],
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "Expected an object" in str(response.json())


@pytest.mark.django_db
def test_put_with_string_screen_id_is_rejected(auth_client, project):
    response = auth_client.put(
        f"/api/projects/{project.id}/screen-assignments/",
        {"task": "abc"},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["task"] == "Invalid screen id."
    assert not ProjectScreenAssignment.objects.filter(project=project, item_type="task").exists()


@pytest.mark.django_db
def test_put_with_boolean_screen_id_is_rejected(auth_client, project):
    response = auth_client.put(
        f"/api/projects/{project.id}/screen-assignments/",
        {"task": True},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["task"] == "Invalid screen id."
    assert not ProjectScreenAssignment.objects.filter(project=project, item_type="task").exists()

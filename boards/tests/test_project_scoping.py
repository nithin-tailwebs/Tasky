import pytest

from boards.models import Board, Card, Comment
from projects.models import Project, ProjectMembership


@pytest.fixture
def foreign_project(other_user):
    project = Project.objects.create(key="FOREIGN", name="Not Yours")
    ProjectMembership.objects.create(project=project, user=other_user, role="owner")
    return project


@pytest.mark.django_db
def test_cannot_create_a_board_in_a_project_you_do_not_belong_to(auth_client, foreign_project):
    response = auth_client.post(
        "/api/boards/",
        {"name": "Sneaky", "project": foreign_project.id},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "project" in response.json()


@pytest.mark.django_db
def test_a_non_member_cannot_retrieve_a_board(auth_client, other_user, foreign_project):
    board = Board.objects.create(name="Hidden", created_by=other_user, project=foreign_project)
    assert auth_client.get(f"/api/boards/{board.id}/").status_code == 403


@pytest.mark.django_db
def test_retrieving_a_nonexistent_board_is_404(auth_client):
    assert auth_client.get("/api/boards/999999/").status_code == 404


@pytest.mark.django_db
def test_a_board_cannot_be_moved_between_projects(auth_client, user, project, foreign_project):
    board = Board.objects.create(name="Mine", created_by=user, project=project)

    response = auth_client.patch(
        f"/api/boards/{board.id}/", {"project": foreign_project.id}, content_type="application/json"
    )

    assert response.status_code == 400
    board.refresh_from_db()
    assert board.project_id == project.id


@pytest.mark.django_db
def test_a_non_member_cannot_list_a_boards_cards(auth_client, other_user, foreign_project):
    board = Board.objects.create(name="Hidden", created_by=other_user, project=foreign_project)
    Card.objects.create(board=board, title="Secret")

    assert auth_client.get(f"/api/boards/{board.id}/cards/").status_code == 403


@pytest.mark.django_db
def test_cards_list_is_scoped_to_my_projects(auth_client, user, project, other_user, foreign_project):
    mine = Board.objects.create(name="Mine", created_by=user, project=project)
    Card.objects.create(board=mine, title="Visible")
    theirs = Board.objects.create(name="Theirs", created_by=other_user, project=foreign_project)
    Card.objects.create(board=theirs, title="Hidden")

    response = auth_client.get("/api/cards/")

    assert response.status_code == 200
    titles = {c["title"] for c in response.json()}
    assert titles == {"Visible"}


@pytest.mark.django_db
def test_a_non_member_cannot_retrieve_a_card(auth_client, other_user, foreign_project):
    board = Board.objects.create(name="Hidden", created_by=other_user, project=foreign_project)
    card = Card.objects.create(board=board, title="Secret")

    assert auth_client.get(f"/api/cards/{card.id}/").status_code == 403


@pytest.mark.django_db
def test_a_non_member_cannot_delete_someones_elses_comment(auth_client, other_user, foreign_project):
    board = Board.objects.create(name="Hidden", created_by=other_user, project=foreign_project)
    card = Card.objects.create(board=board, title="Secret")
    comment = Comment.objects.create(card=card, author=other_user, body="Not yours to see")

    assert auth_client.delete(f"/api/comments/{comment.id}/").status_code == 403


@pytest.mark.django_db
def test_my_tasks_only_shows_tasks_in_my_projects(auth_client, user, project, other_user, foreign_project):
    mine = Board.objects.create(name="Mine", created_by=user, project=project)
    Card.objects.create(board=mine, title="Mine to do", assignee=user)

    theirs = Board.objects.create(name="Theirs", created_by=other_user, project=foreign_project)
    # Same user assigned in a project they've since left/never joined:
    Card.objects.create(board=theirs, title="Not mine to see", assignee=user)

    response = auth_client.get("/api/me/tasks/")

    assert response.status_code == 200
    titles = {c["title"] for c in response.json()}
    assert titles == {"Mine to do"}

import pytest

from boards.models import Board, WorkItem, WorkItemLink


@pytest.fixture
def board(user, project):
    return Board.objects.create(name="Test Board", created_by=user, project=project)


@pytest.fixture
def item_a(board):
    return WorkItem.objects.create(board=board, title="Item A")


@pytest.fixture
def item_b(board):
    return WorkItem.objects.create(board=board, title="Item B")


@pytest.mark.django_db
def test_anonymous_callers_are_rejected(client, item_a):
    assert client.get(f"/api/work-items/{item_a.id}/links/").status_code == 403


@pytest.mark.django_db
def test_creating_a_link(auth_client, item_a, item_b):
    response = auth_client.post(
        f"/api/work-items/{item_a.id}/links/", {"item": item_b.id}, content_type="application/json"
    )
    assert response.status_code == 201
    assert WorkItemLink.objects.filter(item_a=item_a, item_b=item_b).exists()


@pytest.mark.django_db
def test_a_link_is_visible_from_either_side(auth_client, item_a, item_b):
    auth_client.post(f"/api/work-items/{item_a.id}/links/", {"item": item_b.id}, content_type="application/json")

    from_a = auth_client.get(f"/api/work-items/{item_a.id}/links/").json()
    from_b = auth_client.get(f"/api/work-items/{item_b.id}/links/").json()

    assert from_a[0]["item_detail"]["id"] == item_b.id
    assert from_b[0]["item_detail"]["id"] == item_a.id


@pytest.mark.django_db
def test_self_link_is_rejected(auth_client, item_a):
    response = auth_client.post(
        f"/api/work-items/{item_a.id}/links/", {"item": item_a.id}, content_type="application/json"
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_duplicate_link_is_rejected_regardless_of_order(auth_client, item_a, item_b):
    auth_client.post(f"/api/work-items/{item_a.id}/links/", {"item": item_b.id}, content_type="application/json")
    response = auth_client.post(
        f"/api/work-items/{item_b.id}/links/", {"item": item_a.id}, content_type="application/json"
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_linking_a_parent_and_child_is_rejected(auth_client, board, item_a):
    child = WorkItem.objects.create(board=board, title="Child", item_type="story", parent=None)
    # item_a is a plain task; make item_a the parent of an epic-shaped chain isn't valid,
    # so build a real parent/child pair directly instead:
    epic = WorkItem.objects.create(board=board, title="Epic", item_type="epic")
    story = WorkItem.objects.create(board=board, title="Story", item_type="story", parent=epic)

    response = auth_client.post(
        f"/api/work-items/{epic.id}/links/", {"item": story.id}, content_type="application/json"
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_removing_a_link_removes_it_from_both_sides(auth_client, item_a, item_b):
    create_resp = auth_client.post(
        f"/api/work-items/{item_a.id}/links/", {"item": item_b.id}, content_type="application/json"
    )
    link_id = create_resp.json()["id"]

    assert auth_client.delete(f"/api/work-item-links/{link_id}/").status_code == 204
    assert auth_client.get(f"/api/work-items/{item_a.id}/links/").json() == []
    assert auth_client.get(f"/api/work-items/{item_b.id}/links/").json() == []

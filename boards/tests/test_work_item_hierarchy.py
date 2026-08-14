import pytest

from boards.models import Board, WorkItem


@pytest.fixture
def board(user, project):
    return Board.objects.create(name="Test Board", created_by=user, project=project)


@pytest.fixture
def epic(board):
    return WorkItem.objects.create(board=board, title="The epic", item_type="epic")


@pytest.mark.django_db
def test_keys_are_sequential_and_shared_across_types(auth_client, board):
    r1 = auth_client.post("/api/work-items/", {"board": board.id, "item_type": "epic", "title": "E"}, content_type="application/json")
    r2 = auth_client.post("/api/work-items/", {"board": board.id, "item_type": "task", "title": "T"}, content_type="application/json")

    assert r1.json()["key"] == "TASKY-1"
    assert r2.json()["key"] == "TASKY-2"


@pytest.mark.django_db
def test_an_epic_cannot_have_a_parent(auth_client, board, epic):
    other_epic_resp = auth_client.post(
        "/api/work-items/", {"board": board.id, "item_type": "epic", "title": "Other"}, content_type="application/json"
    )
    other_epic_id = other_epic_resp.json()["id"]

    response = auth_client.patch(
        f"/api/work-items/{other_epic_id}/", {"parent": epic.id}, content_type="application/json"
    )
    assert response.status_code == 400
    assert "parent" in response.json()


@pytest.mark.django_db
def test_a_subtask_requires_a_parent(auth_client, board):
    response = auth_client.post(
        "/api/work-items/", {"board": board.id, "item_type": "subtask", "title": "Orphan"}, content_type="application/json"
    )
    assert response.status_code == 400
    assert "parent" in response.json()


@pytest.mark.django_db
def test_a_subtask_cannot_be_parented_to_an_epic(auth_client, board, epic):
    response = auth_client.post(
        "/api/work-items/",
        {"board": board.id, "item_type": "subtask", "title": "Bad", "parent": epic.id},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "parent" in response.json()


@pytest.mark.django_db
def test_a_story_cannot_be_parented_to_a_story(auth_client, board):
    story = WorkItem.objects.create(board=board, title="Story one", item_type="story")
    response = auth_client.post(
        "/api/work-items/",
        {"board": board.id, "item_type": "story", "title": "Story two", "parent": story.id},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "parent" in response.json()


@pytest.mark.django_db
def test_valid_hierarchy_chain_epic_story_subtask(auth_client, board, epic):
    story_resp = auth_client.post(
        "/api/work-items/",
        {"board": board.id, "item_type": "story", "title": "Story", "parent": epic.id},
        content_type="application/json",
    )
    assert story_resp.status_code == 201
    story_id = story_resp.json()["id"]
    assert story_resp.json()["parent_detail"]["key"] == epic.key

    subtask_resp = auth_client.post(
        "/api/work-items/",
        {"board": board.id, "item_type": "subtask", "title": "Subtask", "parent": story_id},
        content_type="application/json",
    )
    assert subtask_resp.status_code == 201


@pytest.mark.django_db
def test_parent_must_be_on_the_same_board(auth_client, board, epic, user, project):
    other_board = Board.objects.create(name="Elsewhere", created_by=user, project=project)
    response = auth_client.post(
        "/api/work-items/",
        {"board": other_board.id, "item_type": "story", "title": "Cross-board", "parent": epic.id},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "parent" in response.json()


@pytest.mark.django_db
def test_item_type_is_immutable(auth_client, board, epic):
    response = auth_client.patch(
        f"/api/work-items/{epic.id}/", {"item_type": "task"}, content_type="application/json"
    )
    assert response.status_code == 400
    assert "item_type" in response.json()


@pytest.mark.django_db
def test_key_is_immutable(auth_client, board, epic):
    response = auth_client.patch(
        f"/api/work-items/{epic.id}/", {"key": "HACK-1"}, content_type="application/json"
    )
    assert response.status_code == 400
    assert "key" in response.json()


@pytest.mark.django_db
def test_reparenting_reuses_the_same_hierarchy_rules(auth_client, board, epic):
    subtask = WorkItem.objects.create(board=board, title="Sub", item_type="subtask", parent=WorkItem.objects.create(board=board, title="Story", item_type="story"))

    response = auth_client.patch(
        f"/api/work-items/{subtask.id}/", {"parent": epic.id}, content_type="application/json"
    )
    assert response.status_code == 400
    assert "parent" in response.json()


@pytest.mark.django_db
def test_deleting_a_parent_orphans_its_children_instead_of_cascading(auth_client, board, epic):
    story = WorkItem.objects.create(board=board, title="Story", item_type="story", parent=epic)

    assert auth_client.delete(f"/api/work-items/{epic.id}/").status_code == 204

    story.refresh_from_db()
    assert story.parent_id is None
    assert WorkItem.objects.filter(id=story.id).exists()


@pytest.mark.django_db
def test_children_endpoint_lists_direct_children_only(auth_client, board, epic):
    story = WorkItem.objects.create(board=board, title="Story", item_type="story", parent=epic)
    WorkItem.objects.create(board=board, title="Grandchild subtask", item_type="subtask", parent=story)

    response = auth_client.get(f"/api/work-items/{epic.id}/children/")

    assert response.status_code == 200
    assert [c["key"] for c in response.json()] == [story.key]


@pytest.mark.django_db
def test_creating_a_work_item_with_parent_but_no_item_type_defaults_to_task(auth_client, board, epic):
    """item_type has a model default (Task) and is required=False on the
    serializer with no serializer-level default, so omitting it drops it
    from validated_data entirely. validate() must resolve it the same way
    the model default would before running hierarchy checks."""
    response = auth_client.post(
        "/api/work-items/",
        {"board": board.id, "title": "Untyped child", "parent": epic.id},
        content_type="application/json",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["item_type"] == "task"
    assert body["parent"] == epic.id
    assert body["parent_detail"]["key"] == epic.key


@pytest.mark.django_db
def test_creating_a_work_item_with_parent_and_no_item_type_does_not_500(auth_client, board, epic):
    """Regression for the crash shape: with item_type omitted, validate()
    used to pass item_type=None straight into hierarchy_error(), which did
    dict(WorkItem.ItemType.choices)[None] and raised an uncaught KeyError,
    surfacing as an unhandled 500 instead of a clean 201 or 400."""
    response = auth_client.post(
        "/api/work-items/",
        {"board": board.id, "title": "Another untyped child", "parent": epic.id},
        content_type="application/json",
    )
    assert response.status_code != 500


@pytest.mark.django_db
def test_retrieving_a_nonexistent_work_item_is_404(auth_client):
    """Closes a gap left open in sub-project 1 (Board had this test, Card
    never did) — a genuinely missing id must 404, distinct from the 403 a
    non-member gets for an id that exists in a project they're not in."""
    assert auth_client.get("/api/work-items/999999/").status_code == 404

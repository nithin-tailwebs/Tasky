import pytest

from boards.models import Board, Card, Comment


@pytest.fixture
def board(user):
    return Board.objects.create(name="Test Board", created_by=user)


@pytest.fixture
def card(board):
    return Card.objects.create(board=board, title="Discuss me")


@pytest.mark.django_db
def test_anonymous_callers_are_rejected(client, card):
    assert client.get(f"/api/cards/{card.id}/comments/").status_code == 403


@pytest.mark.django_db
def test_posting_a_comment_records_the_author(auth_client, card, user):
    response = auth_client.post(
        f"/api/cards/{card.id}/comments/",
        {"body": "Started on this"},
        content_type="application/json",
    )

    assert response.status_code == 201
    assert response.json()["author"]["username"] == "alice"
    assert Comment.objects.get(card=card).author == user


@pytest.mark.django_db
def test_comments_come_back_oldest_first(auth_client, card, user):
    Comment.objects.create(card=card, author=user, body="First")
    Comment.objects.create(card=card, author=user, body="Second")

    response = auth_client.get(f"/api/cards/{card.id}/comments/")

    assert [comment["body"] for comment in response.json()] == ["First", "Second"]


@pytest.mark.django_db
def test_comments_are_scoped_to_their_card(auth_client, board, card, user):
    other_card = Card.objects.create(board=board, title="Elsewhere")
    Comment.objects.create(card=card, author=user, body="Mine")
    Comment.objects.create(card=other_card, author=user, body="Not mine")

    response = auth_client.get(f"/api/cards/{card.id}/comments/")

    assert [comment["body"] for comment in response.json()] == ["Mine"]


@pytest.mark.django_db
def test_an_author_can_delete_their_own_comment(auth_client, card, user):
    comment = Comment.objects.create(card=card, author=user, body="Mine to delete")

    assert auth_client.delete(f"/api/comments/{comment.id}/").status_code == 204
    assert not Comment.objects.filter(id=comment.id).exists()


@pytest.mark.django_db
def test_nobody_can_delete_someone_elses_comment(auth_client, card, other_user):
    comment = Comment.objects.create(card=card, author=other_user, body="Not yours")

    assert auth_client.delete(f"/api/comments/{comment.id}/").status_code == 403
    assert Comment.objects.filter(id=comment.id).exists()


@pytest.mark.django_db
def test_an_authorless_comment_can_be_deleted_by_anyone_signed_in(auth_client, card, other_user):
    """author is SET_NULL when the author's account is deleted. Ownership
    must only be enforced when there IS an owner, or the comment becomes
    permanently undeletable — everyone fails `author != request.user` when
    author is None."""
    comment = Comment.objects.create(card=card, author=other_user, body="Orphaned")
    other_user.delete()
    comment.refresh_from_db()
    assert comment.author_id is None

    assert auth_client.delete(f"/api/comments/{comment.id}/").status_code == 204
    assert not Comment.objects.filter(id=comment.id).exists()


@pytest.mark.django_db
def test_an_empty_comment_is_rejected(auth_client, card):
    response = auth_client.post(
        f"/api/cards/{card.id}/comments/",
        {"body": "   "},
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_deleting_a_card_deletes_its_comments(auth_client, card, user):
    Comment.objects.create(card=card, author=user, body="Goes with the card")
    card.delete()
    assert Comment.objects.count() == 0

import pytest

from projects.models import Invitation, Project, ProjectMembership


@pytest.fixture
def pending_invite(user, other_user):
    project = Project.objects.create(key="TASKY", name="Tasky Redesign")
    ProjectMembership.objects.create(project=project, user=other_user, role="owner")
    return Invitation.objects.create(project=project, invited_user=user, invited_by=other_user)


@pytest.mark.django_db
def test_anonymous_callers_are_rejected(client):
    assert client.get("/api/invitations/").status_code == 403


@pytest.mark.django_db
def test_listing_shows_only_my_pending_invitations(auth_client, pending_invite, other_user):
    already_handled = Invitation.objects.create(
        project=pending_invite.project, invited_user=other_user,
        invited_by=other_user, status=Invitation.Status.ACCEPTED,
    )

    response = auth_client.get("/api/invitations/")

    assert response.status_code == 200
    ids = [i["id"] for i in response.json()]
    assert ids == [pending_invite.id]
    assert already_handled.id not in ids


@pytest.mark.django_db
def test_accepting_creates_a_membership(auth_client, pending_invite, user):
    response = auth_client.post(f"/api/invitations/{pending_invite.id}/accept/")

    assert response.status_code == 204
    pending_invite.refresh_from_db()
    assert pending_invite.status == Invitation.Status.ACCEPTED
    assert ProjectMembership.objects.get(project=pending_invite.project, user=user).role == "member"


@pytest.mark.django_db
def test_declining_does_not_create_a_membership(auth_client, pending_invite, user):
    response = auth_client.post(f"/api/invitations/{pending_invite.id}/decline/")

    assert response.status_code == 204
    pending_invite.refresh_from_db()
    assert pending_invite.status == Invitation.Status.DECLINED
    assert not ProjectMembership.objects.filter(project=pending_invite.project, user=user).exists()


@pytest.mark.django_db
def test_cannot_respond_to_someone_elses_invitation(auth_client, other_user):
    from django.contrib.auth import get_user_model

    third = get_user_model().objects.create_user(username="carol", password="pw-carol-12345")
    project = Project.objects.create(key="TASKY", name="Tasky Redesign")
    ProjectMembership.objects.create(project=project, user=other_user, role="owner")
    someone_elses = Invitation.objects.create(project=project, invited_user=third, invited_by=other_user)

    response = auth_client.post(f"/api/invitations/{someone_elses.id}/accept/")

    assert response.status_code == 403
    assert not ProjectMembership.objects.filter(project=project, user=third).exists()


@pytest.mark.django_db
def test_accepting_an_already_accepted_invitation_is_rejected(auth_client, pending_invite):
    auth_client.post(f"/api/invitations/{pending_invite.id}/accept/")

    response = auth_client.post(f"/api/invitations/{pending_invite.id}/accept/")

    assert response.status_code == 400


@pytest.mark.django_db
def test_re_accepting_after_being_removed_does_not_silently_rejoin(auth_client, pending_invite, user):
    auth_client.post(f"/api/invitations/{pending_invite.id}/accept/")
    ProjectMembership.objects.filter(project=pending_invite.project, user=user).delete()

    response = auth_client.post(f"/api/invitations/{pending_invite.id}/accept/")

    assert response.status_code == 400
    assert not ProjectMembership.objects.filter(project=pending_invite.project, user=user).exists()

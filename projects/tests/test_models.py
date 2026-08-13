import pytest
from django.db import IntegrityError

from projects.models import Invitation, Project, ProjectMembership


@pytest.mark.django_db
def test_project_stringifies_with_its_key():
    project = Project.objects.create(key="TASKY", name="Tasky Redesign")
    assert str(project) == "Tasky Redesign (TASKY)"


@pytest.mark.django_db
def test_project_key_must_be_unique():
    Project.objects.create(key="TASKY", name="First")
    with pytest.raises(IntegrityError):
        Project.objects.create(key="TASKY", name="Second")


@pytest.mark.django_db
def test_a_user_cannot_have_two_memberships_on_the_same_project(user):
    project = Project.objects.create(key="TASKY", name="Tasky Redesign")
    ProjectMembership.objects.create(project=project, user=user, role="owner")
    with pytest.raises(IntegrityError):
        ProjectMembership.objects.create(project=project, user=user, role="admin")


@pytest.mark.django_db
def test_membership_stringifies_with_role_and_project(user):
    project = Project.objects.create(key="TASKY", name="Tasky Redesign")
    membership = ProjectMembership.objects.create(project=project, user=user, role="owner")
    assert str(membership) == f"{user} as owner on {project}"


@pytest.mark.django_db
def test_deleting_a_project_deletes_its_memberships(user):
    project = Project.objects.create(key="TASKY", name="Tasky Redesign")
    ProjectMembership.objects.create(project=project, user=user, role="owner")
    project.delete()
    assert ProjectMembership.objects.count() == 0


@pytest.mark.django_db
def test_invitation_defaults_to_pending(user, other_user):
    project = Project.objects.create(key="TASKY", name="Tasky Redesign")
    invitation = Invitation.objects.create(
        project=project, invited_user=other_user, invited_by=user
    )
    assert invitation.status == Invitation.Status.PENDING


@pytest.mark.django_db
def test_deleting_a_project_deletes_its_invitations(user, other_user):
    project = Project.objects.create(key="TASKY", name="Tasky Redesign")
    Invitation.objects.create(project=project, invited_user=other_user, invited_by=user)
    project.delete()
    assert Invitation.objects.count() == 0

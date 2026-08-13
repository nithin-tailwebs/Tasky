import pytest
from rest_framework.test import APIRequestFactory

from projects.models import Project, ProjectMembership
from projects.serializers import ProjectSerializer


def _request(user):
    request = APIRequestFactory().get("/")
    request.user = user
    return request


@pytest.mark.django_db
def test_my_role_reflects_the_requesting_user(user, other_user):
    project = Project.objects.create(key="TASKY", name="Tasky Redesign")
    ProjectMembership.objects.create(project=project, user=user, role="owner")

    data = ProjectSerializer(project, context={"request": _request(user)}).data
    assert data["my_role"] == "owner"

    data = ProjectSerializer(project, context={"request": _request(other_user)}).data
    assert data["my_role"] is None


@pytest.mark.django_db
def test_member_count_counts_all_roles(user, other_user):
    project = Project.objects.create(key="TASKY", name="Tasky Redesign")
    ProjectMembership.objects.create(project=project, user=user, role="owner")
    ProjectMembership.objects.create(project=project, user=other_user, role="member")

    data = ProjectSerializer(project, context={"request": _request(user)}).data
    assert data["member_count"] == 2


@pytest.mark.django_db
def test_key_is_uppercased_and_validated(user):
    serializer = ProjectSerializer(
        data={"key": "tasky", "name": "Tasky Redesign"}, context={"request": _request(user)}
    )
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["key"] == "TASKY"


@pytest.mark.django_db
def test_key_rejects_bad_formats(user):
    for bad_key in ["T", "toolongkeyyyyy", "TA5KY", ""]:
        serializer = ProjectSerializer(
            data={"key": bad_key, "name": "Tasky Redesign"}, context={"request": _request(user)}
        )
        assert not serializer.is_valid()
        assert "key" in serializer.errors


@pytest.mark.django_db
def test_key_must_be_unique(user):
    Project.objects.create(key="TASKY", name="Existing")
    serializer = ProjectSerializer(
        data={"key": "TASKY", "name": "New"}, context={"request": _request(user)}
    )
    assert not serializer.is_valid()
    assert "key" in serializer.errors

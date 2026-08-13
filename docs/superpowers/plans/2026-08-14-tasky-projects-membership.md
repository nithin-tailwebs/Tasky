# Projects & Membership Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the production Django/DRF backend for Tasky's Projects & Membership feature (sub-project 1 of 7 in the multi-project expansion) — projects, invite-only membership with Owner/Admin/Member roles, and scoping the existing Board/Card/Comment data to project membership.

**Architecture:** A new `projects` Django app owns `Project`, `ProjectMembership`, and `Invitation`. `boards.Board` gains a required `project` FK; `Card` and `Comment` get a `project` property that walks up to it, so a single `IsProjectMember` permission class can authorize all four models uniformly. Role checks are pure functions in `projects/permissions.py` that mirror `design/js/logic.js` from the signed-off prototype exactly, so the two never drift. Existing boards/cards created before this migration are backfilled into a one-off "Legacy Boards" project rather than left dangling.

**Tech Stack:** Django 5.2, Django REST Framework 3.16, MySQL, pytest-django. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-13-tasky-projects-membership-design.md` (signed off 2026-08-13, prototype at `design/` signed off 2026-08-14)

## Global Constraints

- **An unauthenticated call to any endpoint returns `403`, never `401`.** This already falls out of `SessionAuthentication` being the only configured authenticator (`config/settings.py`) — no new code needed for it, but no new code may accidentally add `BasicAuthentication` or any authenticator that emits a `WWW-Authenticate` header, which would flip this to `401`.
- **A non-member touching a project (or a project's boards/cards) they don't belong to gets `403`, not `404`.** A genuinely nonexistent id still gets `404`. This is implemented by keeping `get_object()`'s base queryset unfiltered (so a missing id 404s first) and enforcing membership via `IsProjectMember.has_object_permission` (so an existing-but-inaccessible object 403s). `list` actions are scoped by filtering `get_queryset()` instead — no object exists to 404, so the row is just silently absent from the list.
- **`status` and `board` still cannot be changed via `PATCH` on `/api/cards/{id}/`** — unchanged from the existing implementation in `boards/views.py`. This plan adds the analogous rule that **`project` cannot be changed via `PATCH` on `/api/boards/{id}/`** — boards do not move between projects in this product, mirroring the existing card rule exactly.
- **Role vocabulary is `owner` / `admin` / `member`** (lowercase, matching `ProjectMembership.Role` and the prototype's `design/js/logic.js`). Every serializer, error message, and test uses these exact strings.
- **Every error message string matches the spec's error table** (`docs/superpowers/specs/2026-08-13-tasky-projects-membership-design.md`, "Error handling" section) so the eventual UI can reuse the copy the prototype already uses.
- Every new test file lives under an app's `tests/` package, matching the existing `boards/tests/` and `accounts/tests/` convention — never a bare `tests.py`.

---

## Task 1: `projects` app — Project, ProjectMembership, Invitation models

**Files:**
- Create: `projects/__init__.py`, `projects/apps.py`, `projects/models.py`, `projects/admin.py`
- Create: `projects/migrations/__init__.py`, `projects/migrations/0001_initial.py` (generated)
- Create: `projects/tests/__init__.py`, `projects/tests/test_models.py`
- Modify: `config/settings.py:66-77` (`INSTALLED_APPS`)

**Interfaces:**
- Produces: `projects.models.Project` (`key`, `name`, `description`, `created_at`), `projects.models.ProjectMembership` (`project`, `user`, `role` — one of `ProjectMembership.Role.OWNER`/`ADMIN`/`MEMBER`, `joined_at`), `projects.models.Invitation` (`project`, `invited_user`, `invited_by`, `status` — one of `Invitation.Status.PENDING`/`ACCEPTED`/`DECLINED`, `created_at`, `responded_at`). `Project.memberships` and `Project.invitations` are the reverse related names used by every later task.

- [ ] **Step 1: Scaffold the app**

```bash
python manage.py startapp projects
rm projects/tests.py
mkdir projects/tests
touch projects/tests/__init__.py
```

Edit `projects/apps.py` (`startapp` generates this, but confirm/set it to match the rest of the codebase's convention):

```python
from django.apps import AppConfig


class ProjectsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "projects"
```

Add `'projects'` to `INSTALLED_APPS` in `config/settings.py`, right after `'boards'`:

```python
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'accounts',
    'boards',
    'projects',
]
```

- [ ] **Step 2: Write the failing model tests**

Create `projects/tests/test_models.py`:

```python
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
```

- [ ] **Step 3: Run the tests to confirm they fail**

Run: `docker compose run --rm web pytest projects/tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'projects.models'` (or `ImportError`), since `projects/models.py` doesn't define anything yet.

- [ ] **Step 4: Write the models**

Create `projects/models.py`:

```python
from django.conf import settings
from django.db import models


class Project(models.Model):
    key = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.key})"


class ProjectMembership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        MEMBER = "member", "Member"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="memberships")
    # CASCADE, unlike Board.created_by's SET_NULL: a membership row for a
    # deleted user account is meaningless on its own, whereas a board whose
    # creator is unknown is still a perfectly usable board.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="project_memberships"
    )
    role = models.CharField(max_length=10, choices=Role.choices)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["joined_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["project", "user"], name="unique_project_member"),
        ]

    def __str__(self) -> str:
        return f"{self.user} as {self.role} on {self.project}"


class Invitation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="invitations")
    invited_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="project_invitations_received"
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="project_invitations_sent",
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"invite {self.invited_user} to {self.project} ({self.status})"
```

Create `projects/admin.py`:

```python
from django.contrib import admin

from .models import Invitation, Project, ProjectMembership


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ["key", "name", "created_at"]
    search_fields = ["key", "name"]


@admin.register(ProjectMembership)
class ProjectMembershipAdmin(admin.ModelAdmin):
    list_display = ["project", "user", "role", "joined_at"]
    list_filter = ["role", "project"]


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ["project", "invited_user", "invited_by", "status", "created_at"]
    list_filter = ["status", "project"]
```

Generate the migration:

```bash
python manage.py makemigrations projects -n initial
```

Expected output file: `projects/migrations/0001_initial.py`.

- [ ] **Step 5: Run the tests to confirm they pass**

Run: `docker compose run --rm web pytest projects/tests/test_models.py -v`
Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add projects/ config/settings.py
git commit -m "Add Project, ProjectMembership and Invitation models"
```

---

## Task 2: `Board.project` — schema, legacy backfill, and the existing test suite

**Files:**
- Modify: `boards/models.py:5-21` (`Board`)
- Create: `boards/migrations/0004_board_project_nullable.py` (generated), `boards/migrations/0005_backfill_legacy_project.py` (hand-written), `boards/migrations/0006_board_project_required.py` (generated)
- Modify: `boards/management/commands/seed_demo.py`
- Modify: `conftest.py`
- Modify: `boards/tests/test_board_api.py`, `boards/tests/test_board_model.py`, `boards/tests/test_card_api.py`, `boards/tests/test_card_model.py`, `boards/tests/test_card_move.py`, `boards/tests/test_comments.py`, `boards/tests/test_my_tasks.py`

**Interfaces:**
- Consumes: `projects.models.Project`, `projects.models.ProjectMembership` (Task 1)
- Produces: `Board.project` (required FK to `Project`, `related_name="boards"`). A root-level `project` pytest fixture (`conftest.py`) that every later boards/cards test and every Task 3+ test can depend on: a `Project` owned by the `user` fixture.

This task doesn't follow strict red-green TDD, because there's no new *behavior* to test-first here — it's a schema migration that must land without breaking the 92 existing tests. The check for correctness is "the full suite is still green," which is Step 8.

- [ ] **Step 1: Add the FK as nullable**

In `boards/models.py`, add to `Board` (right after `description`):

```python
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="boards", null=True
    )
```

```bash
python manage.py makemigrations boards -n board_project_nullable
```

Expected output file: `boards/migrations/0004_board_project_nullable.py`.

- [ ] **Step 2: Write the data migration**

```bash
python manage.py makemigrations boards --empty -n backfill_legacy_project
```

Expected output file: `boards/migrations/0005_backfill_legacy_project.py`. Replace its contents with:

```python
from django.db import migrations


def backfill_legacy_project(apps, schema_editor):
    Project = apps.get_model("projects", "Project")
    ProjectMembership = apps.get_model("projects", "ProjectMembership")
    Board = apps.get_model("boards", "Board")
    Card = apps.get_model("boards", "Card")
    User = apps.get_model("accounts", "User")

    orphan_boards = Board.objects.filter(project__isnull=True)
    if not orphan_boards.exists():
        return  # Fresh database (e.g. every test run) — nothing to backfill.

    owner = (
        User.objects.filter(is_superuser=True).order_by("date_joined", "id").first()
        or User.objects.order_by("date_joined", "id").first()
    )
    if owner is None:
        return  # No users exist yet either — nothing to assign ownership to.

    project = Project.objects.create(
        key="LEGACY",
        name="Legacy Boards",
        description="Boards that existed before projects were introduced.",
    )
    ProjectMembership.objects.create(project=project, user_id=owner.id, role="owner")

    board_ids = list(orphan_boards.values_list("id", flat=True))
    referenced_user_ids = (
        set(orphan_boards.exclude(created_by__isnull=True).values_list("created_by_id", flat=True))
        | set(
            Card.objects.filter(board_id__in=board_ids, created_by__isnull=False)
            .values_list("created_by_id", flat=True)
        )
        | set(
            Card.objects.filter(board_id__in=board_ids, assignee__isnull=False)
            .values_list("assignee_id", flat=True)
        )
    )
    referenced_user_ids.discard(owner.id)

    ProjectMembership.objects.bulk_create(
        ProjectMembership(project=project, user_id=uid, role="member")
        for uid in referenced_user_ids
    )

    orphan_boards.update(project=project)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("boards", "0004_board_project_nullable"),
        ("projects", "0001_initial"),
    ]
    operations = [
        migrations.RunPython(backfill_legacy_project, noop_reverse),
    ]
```

- [ ] **Step 3: Make the field required**

In `boards/models.py`, remove `null=True` from the `project` field:

```python
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="boards")
```

```bash
python manage.py makemigrations boards -n board_project_required
```

Expected output file: `boards/migrations/0006_board_project_required.py`.

- [ ] **Step 4: Add the `project` fixture**

In `conftest.py`, add (after the existing fixtures):

```python
@pytest.fixture
def project(user):
    from projects.models import Project, ProjectMembership

    project = Project.objects.create(key="TASKY", name="Tasky Redesign")
    ProjectMembership.objects.create(project=project, user=user, role="owner")
    return project
```

- [ ] **Step 5: Update `seed_demo`**

In `boards/management/commands/seed_demo.py`:

```python
from boards.models import Board, Card
from projects.models import Project, ProjectMembership
```

In `Command.handle`, right after the `people` loop and before the `for index, (board_name, cards)` loop:

```python
        project, _ = Project.objects.get_or_create(
            key="TASKY",
            defaults={"name": "Tasky Demo", "description": "Seeded demo project."},
        )
        for index, person in enumerate(people):
            ProjectMembership.objects.get_or_create(
                project=project,
                user=person,
                defaults={"role": "owner" if index == 0 else "member"},
            )
```

Then add `"project": project,` to the `defaults` dict inside the board-creation loop:

```python
            board, created = Board.objects.get_or_create(
                name=board_name,
                defaults={
                    "description": f"Demo board: {board_name}",
                    "created_by": people[0],
                    "project": project,
                },
            )
```

- [ ] **Step 6: Update every existing test that creates a `Board`**

In `boards/tests/test_board_api.py` — add the import, rewrite `test_listing_returns_every_board` into a project-scoped version, and thread `project` through the other board-creating tests:

```python
import pytest

from boards.models import Board
from projects.models import Project, ProjectMembership


@pytest.mark.django_db
def test_anonymous_callers_are_rejected(client):
    assert client.get("/api/boards/").status_code == 403


@pytest.mark.django_db
def test_listing_returns_only_boards_in_my_projects(auth_client, user, other_user, project):
    Board.objects.create(name="Mine", created_by=user, project=project)

    other_project = Project.objects.create(key="OTHER", name="Someone Else's Project")
    ProjectMembership.objects.create(project=other_project, user=other_user, role="owner")
    Board.objects.create(name="Not mine", created_by=other_user, project=other_project)

    response = auth_client.get("/api/boards/")

    assert response.status_code == 200
    names = {board["name"] for board in response.json()}
    assert names == {"Mine"}


@pytest.mark.django_db
def test_creating_a_board_records_the_creator(auth_client, user, project):
    response = auth_client.post(
        "/api/boards/",
        {"name": "Q3 Launch", "description": "Everything for the launch", "project": project.id},
        content_type="application/json",
    )

    assert response.status_code == 201
    assert response.json()["created_by"]["username"] == "alice"
    assert Board.objects.get(name="Q3 Launch").created_by == user


@pytest.mark.django_db
def test_created_by_cannot_be_forged(auth_client, other_user, project):
    response = auth_client.post(
        "/api/boards/",
        {"name": "Spoofed", "created_by": other_user.id, "project": project.id},
        content_type="application/json",
    )

    assert response.status_code == 201
    assert Board.objects.get(name="Spoofed").created_by.username == "alice"


@pytest.mark.django_db
def test_a_board_can_be_renamed(auth_client, user, project):
    board = Board.objects.create(name="Old Name", created_by=user, project=project)

    response = auth_client.patch(
        f"/api/boards/{board.id}/",
        {"name": "New Name"},
        content_type="application/json",
    )

    assert response.status_code == 200
    board.refresh_from_db()
    assert board.name == "New Name"


@pytest.mark.django_db
def test_a_board_can_be_deleted(auth_client, user, project):
    board = Board.objects.create(name="Doomed", created_by=user, project=project)

    assert auth_client.delete(f"/api/boards/{board.id}/").status_code == 204
    assert not Board.objects.filter(id=board.id).exists()


@pytest.mark.django_db
def test_name_is_required(auth_client):
    response = auth_client.post(
        "/api/boards/", {"description": "no name"}, content_type="application/json"
    )
    assert response.status_code == 400
    assert "name" in response.json()
```

In `boards/tests/test_board_model.py` — thread `project` through every test:

```python
import pytest

from boards.models import Board


@pytest.mark.django_db
def test_board_stringifies_to_its_name(user, project):
    board = Board.objects.create(name="Website Redesign", created_by=user, project=project)
    assert str(board) == "Website Redesign"


@pytest.mark.django_db
def test_description_is_optional(user, project):
    board = Board.objects.create(name="Ops", created_by=user, project=project)
    assert board.description == ""


@pytest.mark.django_db
def test_boards_are_ordered_newest_first(user, project):
    first = Board.objects.create(name="First", created_by=user, project=project)
    second = Board.objects.create(name="Second", created_by=user, project=project)
    assert list(Board.objects.all()) == [second, first]


@pytest.mark.django_db
def test_board_survives_its_creator_being_deleted(user, project):
    board = Board.objects.create(name="Orphan", created_by=user, project=project)
    user.delete()
    board.refresh_from_db()
    assert board.created_by is None
```

In `boards/tests/test_card_api.py`, `boards/tests/test_card_model.py`, `boards/tests/test_card_move.py`, `boards/tests/test_comments.py` — each has this `board` fixture:

```python
@pytest.fixture
def board(user):
    return Board.objects.create(name="Test Board", created_by=user)
```

Replace it in all four files with:

```python
@pytest.fixture
def board(user, project):
    return Board.objects.create(name="Test Board", created_by=user, project=project)
```

Then, in `boards/tests/test_card_api.py`, add `project=project` (and `project` to the test's parameters) to the three inline `Board.objects.create(name="Elsewhere", created_by=user)` calls — in `test_listing_a_boards_cards`, `test_listing_all_cards_is_unscoped_by_board`, and `test_patching_board_is_rejected`:

```python
@pytest.mark.django_db
def test_listing_a_boards_cards(auth_client, board, user, project):
    Card.objects.create(board=board, title="First", position=0)
    Card.objects.create(board=board, title="Second", position=1)
    other_board = Board.objects.create(name="Elsewhere", created_by=user, project=project)
    Card.objects.create(board=other_board, title="Not mine")
    ...
```

```python
@pytest.mark.django_db
def test_listing_all_cards_is_unscoped_by_board(auth_client, board, user, project):
    other_board = Board.objects.create(name="Elsewhere", created_by=user, project=project)
    ...
```

```python
@pytest.mark.django_db
def test_patching_board_is_rejected(auth_client, board, user, project):
    other_board = Board.objects.create(name="Elsewhere", created_by=user, project=project)
    ...
```

In `boards/tests/test_card_move.py`, do the same for `test_a_move_never_touches_another_board`:

```python
@pytest.mark.django_db
def test_a_move_never_touches_another_board(auth_client, board, todo_cards, user, project):
    other_board = Board.objects.create(name="Elsewhere", created_by=user, project=project)
    ...
```

In `boards/tests/test_my_tasks.py`, update the `board` fixture the same way as above, and thread `project` through `test_my_cards_span_every_board`:

```python
@pytest.fixture
def board(user, project):
    return Board.objects.create(name="Test Board", created_by=user, project=project)


...


@pytest.mark.django_db
def test_my_cards_span_every_board(auth_client, board, user, project):
    second_board = Board.objects.create(name="Second", created_by=user, project=project)
    ...
```

- [ ] **Step 7: Run migrations locally**

Run: `docker compose run --rm web python manage.py migrate`
Expected: all six new migrations apply cleanly (0001 for `projects`, 0004–0006 for `boards`).

- [ ] **Step 8: Run the full suite**

Run: `docker compose run --rm web pytest -v`
Expected: all tests pass (92 existing + 7 new model tests from Task 1). If any board/card test still fails, it's almost certainly a missed `Board.objects.create(...)` call site — grep for `Board.objects.create` across `boards/tests/` and confirm every call now passes `project=`.

- [ ] **Step 9: Commit**

```bash
git add boards/ conftest.py
git commit -m "Add required Board.project FK, backfilling existing boards into a Legacy project"
```

---

## Task 3: Role-permission rules and the `IsProjectMember` permission class

**Files:**
- Create: `projects/permissions.py`
- Test: `projects/tests/test_permissions.py`

**Interfaces:**
- Consumes: `projects.models.Project` (Task 1)
- Produces: `can_invite(role)`, `can_remove(acting_role, target_role)`, `can_change_role(acting_role)`, `can_transfer_ownership(acting_role)`, `can_delete_project(acting_role)`, `can_leave(acting_role)` — all pure functions taking/returning role strings. `IsProjectMember` — a DRF `BasePermission` subclass whose `has_object_permission` accepts any object that either *is* a `Project` or has a `.project` property/attribute pointing to one.

- [ ] **Step 1: Write the failing tests**

Create `projects/tests/test_permissions.py`:

```python
from projects.permissions import (
    can_change_role,
    can_delete_project,
    can_invite,
    can_leave,
    can_remove,
    can_transfer_ownership,
)


def test_owner_can_manage_but_not_leave_without_transferring():
    assert can_invite("owner")
    assert can_change_role("owner")
    assert can_transfer_ownership("owner")
    assert can_delete_project("owner")
    assert not can_leave("owner")


def test_admin_can_invite_and_leave_but_not_manage_roles_or_delete():
    assert can_invite("admin")
    assert can_leave("admin")
    assert not can_change_role("admin")
    assert not can_transfer_ownership("admin")
    assert not can_delete_project("admin")


def test_member_can_only_leave():
    assert can_leave("member")
    assert not can_invite("member")
    assert not can_change_role("member")
    assert not can_transfer_ownership("member")
    assert not can_delete_project("member")


def test_remove_matrix():
    assert can_remove("owner", "admin")
    assert can_remove("owner", "member")
    assert not can_remove("owner", "owner")
    assert can_remove("admin", "member")
    assert not can_remove("admin", "admin")
    assert not can_remove("admin", "owner")
    assert not can_remove("member", "member")
    assert not can_remove("member", "admin")
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `docker compose run --rm web pytest projects/tests/test_permissions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'projects.permissions'`.

- [ ] **Step 3: Write the permission rules**

Create `projects/permissions.py`:

```python
"""Pure role-permission rules — mirrors the matrix in
docs/superpowers/specs/2026-08-13-tasky-projects-membership-design.md
and design/js/logic.js exactly, so the three stay in lockstep."""

from rest_framework.permissions import BasePermission

from .models import Project

OWNER = "owner"
ADMIN = "admin"
MEMBER = "member"


def can_invite(role):
    return role in (OWNER, ADMIN)


def can_remove(acting_role, target_role):
    return (acting_role == OWNER and target_role != OWNER) or (
        acting_role == ADMIN and target_role == MEMBER
    )


def can_change_role(acting_role):
    return acting_role == OWNER


def can_transfer_ownership(acting_role):
    return acting_role == OWNER


def can_delete_project(acting_role):
    return acting_role == OWNER


def can_leave(acting_role):
    return acting_role in (ADMIN, MEMBER)


class IsProjectMember(BasePermission):
    """Object-level only — it only ever sees objects the queryset already
    found, so a genuinely missing id 404s before this runs. This is what
    turns "found, but not one of your projects" into 403 instead of a
    leaked 404."""

    message = "You don't have access to this project."

    def has_object_permission(self, request, view, obj):
        project = obj if isinstance(obj, Project) else obj.project
        return project.memberships.filter(user=request.user).exists()
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `docker compose run --rm web pytest projects/tests/test_permissions.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add projects/permissions.py projects/tests/test_permissions.py
git commit -m "Add role-permission rules and the IsProjectMember permission class"
```

---

## Task 4: Serializers

**Files:**
- Create: `projects/serializers.py`
- Test: `projects/tests/test_serializers.py`

**Interfaces:**
- Consumes: `projects.models.*` (Task 1), `accounts.serializers.UserSerializer`
- Produces: `ProjectSerializer` (fields `id, key, name, description, my_role, member_count, created_at`; `my_role` needs `context["request"].user`), `ProjectMembershipSerializer` (`id, user_detail, role, joined_at`), `ChangeRoleSerializer` (`role`), `TransferOwnershipSerializer` (`user_id` → `validated_data["user"]`), `InviteSerializer` (`user_id` → `validated_data["user"]`), `InvitationSerializer` (`id, project_detail, invited_by_detail, status, created_at`).

- [ ] **Step 1: Write the failing tests**

Create `projects/tests/test_serializers.py`:

```python
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
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `docker compose run --rm web pytest projects/tests/test_serializers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'projects.serializers'`.

- [ ] **Step 3: Write the serializers**

Create `projects/serializers.py`:

```python
import re

from django.contrib.auth import get_user_model
from rest_framework import serializers

from accounts.serializers import UserSerializer

from .models import Invitation, Project, ProjectMembership

KEY_PATTERN = re.compile(r"^[A-Z]{2,10}$")


class ProjectSerializer(serializers.ModelSerializer):
    my_role = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = ["id", "key", "name", "description", "my_role", "member_count", "created_at"]
        read_only_fields = ["created_at"]

    def get_my_role(self, obj):
        membership = obj.memberships.filter(user=self.context["request"].user).first()
        return membership.role if membership else None

    def get_member_count(self, obj):
        return obj.memberships.count()

    def validate_key(self, value):
        value = value.strip().upper()
        if not KEY_PATTERN.match(value):
            raise serializers.ValidationError("Key must be 2–10 letters, e.g. TASKY.")
        if Project.objects.filter(key=value).exists():
            raise serializers.ValidationError(f'"{value}" is already taken.')
        return value


class ProjectMembershipSerializer(serializers.ModelSerializer):
    user_detail = UserSerializer(source="user", read_only=True)

    class Meta:
        model = ProjectMembership
        fields = ["id", "user_detail", "role", "joined_at"]


class ChangeRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=[ProjectMembership.Role.ADMIN, ProjectMembership.Role.MEMBER])


class TransferOwnershipSerializer(serializers.Serializer):
    user_id = serializers.PrimaryKeyRelatedField(queryset=get_user_model().objects.all(), source="user")


class InviteSerializer(serializers.Serializer):
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=get_user_model().objects.filter(is_active=True), source="user"
    )


class InvitationSerializer(serializers.ModelSerializer):
    project_detail = ProjectSerializer(source="project", read_only=True)
    invited_by_detail = UserSerializer(source="invited_by", read_only=True)

    class Meta:
        model = Invitation
        fields = ["id", "project_detail", "invited_by_detail", "status", "created_at"]
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `docker compose run --rm web pytest projects/tests/test_serializers.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add projects/serializers.py projects/tests/test_serializers.py
git commit -m "Add Project/Membership/Invitation serializers"
```

---

## Task 5: `ProjectViewSet` — list, create, retrieve, delete

**Files:**
- Create: `projects/views.py`, `projects/urls.py`
- Modify: `config/urls.py:7-11`
- Test: `projects/tests/test_project_api.py`

**Interfaces:**
- Consumes: `ProjectSerializer` (Task 4), `IsProjectMember`, `can_delete_project` (Task 3)
- Produces: `GET/POST /api/projects/`, `GET/DELETE /api/projects/{id}/`, all registered under router `basename="project"`. Later tasks (6–8) add more actions onto the same `ProjectViewSet` class defined here.

- [ ] **Step 1: Write the failing tests**

Create `projects/tests/test_project_api.py`:

```python
import pytest

from projects.models import Project, ProjectMembership


@pytest.mark.django_db
def test_anonymous_callers_are_rejected(client):
    assert client.get("/api/projects/").status_code == 403


@pytest.mark.django_db
def test_listing_returns_only_my_projects(auth_client, user, other_user):
    mine = Project.objects.create(key="MINE", name="Mine")
    ProjectMembership.objects.create(project=mine, user=user, role="owner")

    theirs = Project.objects.create(key="THEIRS", name="Theirs")
    ProjectMembership.objects.create(project=theirs, user=other_user, role="owner")

    response = auth_client.get("/api/projects/")

    assert response.status_code == 200
    keys = {p["key"] for p in response.json()}
    assert keys == {"MINE"}


@pytest.mark.django_db
def test_creating_a_project_makes_the_creator_owner(auth_client, user):
    response = auth_client.post(
        "/api/projects/", {"key": "tasky", "name": "Tasky Redesign"}, content_type="application/json"
    )

    assert response.status_code == 201
    body = response.json()
    assert body["key"] == "TASKY"
    assert body["my_role"] == "owner"
    assert ProjectMembership.objects.get(project_id=body["id"], user=user).role == "owner"


@pytest.mark.django_db
def test_creating_a_project_with_a_duplicate_key_is_rejected(auth_client):
    Project.objects.create(key="TASKY", name="Existing")

    response = auth_client.post(
        "/api/projects/", {"key": "TASKY", "name": "New"}, content_type="application/json"
    )

    assert response.status_code == 400
    assert "key" in response.json()


@pytest.mark.django_db
def test_retrieving_a_nonexistent_project_is_404(auth_client):
    assert auth_client.get("/api/projects/999999/").status_code == 404


@pytest.mark.django_db
def test_a_non_member_gets_403_not_404(auth_client, other_user):
    theirs = Project.objects.create(key="THEIRS", name="Theirs")
    ProjectMembership.objects.create(project=theirs, user=other_user, role="owner")

    response = auth_client.get(f"/api/projects/{theirs.id}/")

    assert response.status_code == 403


@pytest.mark.django_db
def test_only_the_owner_can_delete_a_project(auth_client, user, other_user):
    project = Project.objects.create(key="TASKY", name="Tasky Redesign")
    ProjectMembership.objects.create(project=project, user=user, role="admin")
    ProjectMembership.objects.create(project=project, user=other_user, role="owner")

    response = auth_client.delete(f"/api/projects/{project.id}/")

    assert response.status_code == 403
    assert Project.objects.filter(id=project.id).exists()


@pytest.mark.django_db
def test_the_owner_can_delete_a_project(auth_client, user):
    project = Project.objects.create(key="TASKY", name="Tasky Redesign")
    ProjectMembership.objects.create(project=project, user=user, role="owner")

    response = auth_client.delete(f"/api/projects/{project.id}/")

    assert response.status_code == 204
    assert not Project.objects.filter(id=project.id).exists()


@pytest.mark.django_db
def test_deleting_a_project_cascades_to_its_boards(auth_client, user):
    from boards.models import Board

    project = Project.objects.create(key="TASKY", name="Tasky Redesign")
    ProjectMembership.objects.create(project=project, user=user, role="owner")
    board = Board.objects.create(name="Doomed", created_by=user, project=project)

    auth_client.delete(f"/api/projects/{project.id}/")

    assert not Board.objects.filter(id=board.id).exists()
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `docker compose run --rm web pytest projects/tests/test_project_api.py -v`
Expected: FAIL — `404` for every URL, since `/api/projects/` doesn't exist yet.

- [ ] **Step 3: Write the view and wire the URLs**

Create `projects/views.py`:

```python
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated

from .models import Project, ProjectMembership
from .permissions import IsProjectMember, can_delete_project
from .serializers import ProjectSerializer


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated, IsProjectMember]
    pagination_class = None

    def get_queryset(self):
        qs = Project.objects.all()
        if self.action == "list":
            qs = qs.filter(memberships__user=self.request.user).distinct()
        return qs

    def perform_create(self, serializer):
        project = serializer.save()
        ProjectMembership.objects.create(
            project=project, user=self.request.user, role=ProjectMembership.Role.OWNER
        )

    def perform_destroy(self, instance):
        membership = instance.memberships.get(user=self.request.user)
        if not can_delete_project(membership.role):
            raise PermissionDenied("Only the owner can delete a project.")
        instance.delete()
```

Create `projects/urls.py`:

```python
from rest_framework.routers import DefaultRouter

from .views import ProjectViewSet

router = DefaultRouter()
router.register("projects", ProjectViewSet, basename="project")

urlpatterns = router.urls
```

In `config/urls.py`, add the include (after the `boards.urls` include):

```python
    path("api/", include("accounts.urls")),
    path("api/", include("boards.urls")),
    path("api/", include("projects.urls")),
    path("api/me/tasks/", MyTasksView.as_view(), name="my-tasks"),
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `docker compose run --rm web pytest projects/tests/test_project_api.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add projects/views.py projects/urls.py config/urls.py projects/tests/test_project_api.py
git commit -m "Add ProjectViewSet: list, create, retrieve, delete"
```

---

## Task 6: Members — list, remove, change role

**Files:**
- Modify: `projects/views.py`
- Test: `projects/tests/test_membership_api.py`

**Interfaces:**
- Consumes: `ProjectMembershipSerializer`, `ChangeRoleSerializer` (Task 4), `can_remove`, `can_change_role` (Task 3)
- Produces: `GET /api/projects/{id}/members/`, `DELETE /api/projects/{id}/members/{user_id}/`, `POST /api/projects/{id}/members/{user_id}/role/`.

- [ ] **Step 1: Write the failing tests**

Create `projects/tests/test_membership_api.py`:

```python
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
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `docker compose run --rm web pytest projects/tests/test_membership_api.py -v`
Expected: FAIL — `404` on every `/members/...` URL, since the actions don't exist yet.

- [ ] **Step 3: Add the actions**

In `projects/views.py`, add these imports and the three `@action` methods to `ProjectViewSet`:

```python
from django.shortcuts import get_object_or_404
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from .permissions import IsProjectMember, can_change_role, can_delete_project, can_leave, can_remove
from .serializers import ChangeRoleSerializer, ProjectMembershipSerializer, ProjectSerializer

ROLE_ORDER = {"owner": 0, "admin": 1, "member": 2}
```

```python
    @action(detail=True, methods=["get"], url_path="members")
    def members(self, request, pk=None):
        project = self.get_object()
        memberships = sorted(
            project.memberships.select_related("user"),
            key=lambda m: (ROLE_ORDER[m.role], m.id),
        )
        return Response(ProjectMembershipSerializer(memberships, many=True).data)

    @action(detail=True, methods=["delete"], url_path=r"members/(?P<user_id>[^/.]+)")
    def remove_member(self, request, pk=None, user_id=None):
        """Doubles as "leave": removing your own membership is only ever
        blocked for the Owner (who must transfer ownership first). Removing
        someone else goes through the normal can_remove role matrix."""
        project = self.get_object()
        acting = project.memberships.get(user=request.user)
        target = get_object_or_404(ProjectMembership, project=project, user_id=user_id)

        if target.user_id == request.user.id:
            if not can_leave(acting.role):
                raise ValidationError(
                    {"detail": "Transfer ownership before leaving a project you own."}
                )
            target.delete()
            return Response(status=204)

        if not can_remove(acting.role, target.role):
            raise PermissionDenied("You don't have permission to remove this member.")

        target.delete()
        return Response(status=204)

    @action(detail=True, methods=["post"], url_path=r"members/(?P<user_id>[^/.]+)/role")
    def change_role(self, request, pk=None, user_id=None):
        project = self.get_object()
        acting = project.memberships.get(user=request.user)
        if not can_change_role(acting.role):
            raise PermissionDenied("Only the owner can change member roles.")

        serializer = ChangeRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        target = get_object_or_404(ProjectMembership, project=project, user_id=user_id)
        if target.role == ProjectMembership.Role.OWNER:
            raise PermissionDenied(
                "The owner's role can't be changed here — transfer ownership instead."
            )
        target.role = serializer.validated_data["role"]
        target.save()
        return Response(ProjectMembershipSerializer(target).data)
```

Also replace the hand-rolled check in `perform_destroy` (from Task 5) with the same imported helper for consistency — it already imports `can_delete_project`, so no change needed there.

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `docker compose run --rm web pytest projects/tests/test_membership_api.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add projects/views.py projects/tests/test_membership_api.py
git commit -m "Add member listing, removal, and role changes"
```

---

## Task 7: Transfer ownership and invite

**Files:**
- Modify: `projects/views.py`
- Test: `projects/tests/test_transfer_and_invite_api.py`

**Interfaces:**
- Consumes: `TransferOwnershipSerializer`, `InviteSerializer`, `InvitationSerializer` (Task 4), `can_transfer_ownership`, `can_invite` (Task 3)
- Produces: `POST /api/projects/{id}/transfer-ownership/`, `POST /api/projects/{id}/invite/`.

- [ ] **Step 1: Write the failing tests**

Create `projects/tests/test_transfer_and_invite_api.py`:

```python
import pytest

from projects.models import Invitation, Project, ProjectMembership


@pytest.fixture
def owned_project(user, other_user):
    project = Project.objects.create(key="TASKY", name="Tasky Redesign")
    ProjectMembership.objects.create(project=project, user=user, role="owner")
    ProjectMembership.objects.create(project=project, user=other_user, role="admin")
    return project


@pytest.mark.django_db
def test_owner_can_transfer_to_an_admin(auth_client, owned_project, user, other_user):
    response = auth_client.post(f"/api/projects/{owned_project.id}/transfer-ownership/",
                                 {"user_id": other_user.id}, content_type="application/json")

    assert response.status_code == 204
    assert ProjectMembership.objects.get(project=owned_project, user=user).role == "admin"
    assert ProjectMembership.objects.get(project=owned_project, user=other_user).role == "owner"


@pytest.mark.django_db
def test_cannot_transfer_to_a_plain_member(auth_client, owned_project, user):
    from django.contrib.auth import get_user_model

    plain = get_user_model().objects.create_user(username="carol", password="pw-carol-12345")
    ProjectMembership.objects.create(project=owned_project, user=plain, role="member")

    response = auth_client.post(f"/api/projects/{owned_project.id}/transfer-ownership/",
                                 {"user_id": plain.id}, content_type="application/json")

    assert response.status_code == 400
    assert ProjectMembership.objects.get(project=owned_project, user=user).role == "owner"


@pytest.mark.django_db
def test_admin_cannot_transfer_ownership(auth_client, other_user, owned_project):
    auth_client.logout()
    auth_client.force_login(other_user)

    response = auth_client.post(f"/api/projects/{owned_project.id}/transfer-ownership/",
                                 {"user_id": other_user.id}, content_type="application/json")

    assert response.status_code == 403


@pytest.mark.django_db
def test_owner_can_invite_a_non_member(auth_client, owned_project):
    from django.contrib.auth import get_user_model

    outsider = get_user_model().objects.create_user(username="carol", password="pw-carol-12345")

    response = auth_client.post(f"/api/projects/{owned_project.id}/invite/",
                                 {"user_id": outsider.id}, content_type="application/json")

    assert response.status_code == 201
    invitation = Invitation.objects.get(project=owned_project, invited_user=outsider)
    assert invitation.status == Invitation.Status.PENDING


@pytest.mark.django_db
def test_admin_can_also_invite(auth_client, other_user, owned_project):
    from django.contrib.auth import get_user_model

    outsider = get_user_model().objects.create_user(username="carol", password="pw-carol-12345")
    auth_client.logout()
    auth_client.force_login(other_user)  # admin

    response = auth_client.post(f"/api/projects/{owned_project.id}/invite/",
                                 {"user_id": outsider.id}, content_type="application/json")

    assert response.status_code == 201


@pytest.mark.django_db
def test_member_cannot_invite(auth_client, owned_project):
    from django.contrib.auth import get_user_model

    plain = get_user_model().objects.create_user(username="carol", password="pw-carol-12345")
    ProjectMembership.objects.create(project=owned_project, user=plain, role="member")
    outsider = get_user_model().objects.create_user(username="dave", password="pw-dave-12345")

    auth_client.logout()
    auth_client.force_login(plain)

    response = auth_client.post(f"/api/projects/{owned_project.id}/invite/",
                                 {"user_id": outsider.id}, content_type="application/json")

    assert response.status_code == 403


@pytest.mark.django_db
def test_inviting_an_existing_member_is_rejected(auth_client, owned_project, other_user):
    response = auth_client.post(f"/api/projects/{owned_project.id}/invite/",
                                 {"user_id": other_user.id}, content_type="application/json")

    assert response.status_code == 400


@pytest.mark.django_db
def test_inviting_someone_twice_is_rejected(auth_client, owned_project):
    from django.contrib.auth import get_user_model

    outsider = get_user_model().objects.create_user(username="carol", password="pw-carol-12345")
    auth_client.post(f"/api/projects/{owned_project.id}/invite/",
                      {"user_id": outsider.id}, content_type="application/json")

    response = auth_client.post(f"/api/projects/{owned_project.id}/invite/",
                                 {"user_id": outsider.id}, content_type="application/json")

    assert response.status_code == 400
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `docker compose run --rm web pytest projects/tests/test_transfer_and_invite_api.py -v`
Expected: FAIL — `404` on both URLs, since the actions don't exist yet.

- [ ] **Step 3: Add the actions**

In `projects/views.py`, replace the whole import block at the top of the file with (this supersedes the imports from Tasks 5 and 6 — it's the full set the file needs from this point on, including `can_leave`, which Task 6's `remove_member` still relies on):

```python
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Invitation, Project, ProjectMembership
from .permissions import (
    IsProjectMember,
    can_change_role,
    can_delete_project,
    can_invite,
    can_leave,
    can_remove,
    can_transfer_ownership,
)
from .serializers import (
    ChangeRoleSerializer,
    InvitationSerializer,
    InviteSerializer,
    ProjectMembershipSerializer,
    ProjectSerializer,
    TransferOwnershipSerializer,
)
```

Add to `ProjectViewSet`:

```python
    @action(detail=True, methods=["post"], url_path="transfer-ownership")
    def transfer_ownership(self, request, pk=None):
        project = self.get_object()
        acting = project.memberships.get(user=request.user)
        if not can_transfer_ownership(acting.role):
            raise PermissionDenied("Only the owner can transfer ownership.")

        serializer = TransferOwnershipSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_owner = serializer.validated_data["user"]

        target = project.memberships.filter(user=new_owner, role=ProjectMembership.Role.ADMIN).first()
        if target is None:
            raise ValidationError(
                {"user_id": "Ownership can only be transferred to an existing Admin."}
            )

        with transaction.atomic():
            acting.role = ProjectMembership.Role.ADMIN
            acting.save()
            target.role = ProjectMembership.Role.OWNER
            target.save()
        return Response(status=204)

    @action(detail=True, methods=["post"], url_path="invite")
    def invite(self, request, pk=None):
        project = self.get_object()
        acting = project.memberships.get(user=request.user)
        if not can_invite(acting.role):
            raise PermissionDenied("You don't have permission to invite members.")

        serializer = InviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invited_user = serializer.validated_data["user"]

        if project.memberships.filter(user=invited_user).exists():
            raise ValidationError({"user_id": "Already a member of this project."})
        if Invitation.objects.filter(
            project=project, invited_user=invited_user, status=Invitation.Status.PENDING
        ).exists():
            raise ValidationError({"user_id": "Already invited — waiting on a response."})

        invitation = Invitation.objects.create(
            project=project, invited_user=invited_user, invited_by=request.user
        )
        return Response(
            InvitationSerializer(invitation, context={"request": request}).data, status=201
        )
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `docker compose run --rm web pytest projects/tests/test_transfer_and_invite_api.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add projects/views.py projects/tests/test_transfer_and_invite_api.py
git commit -m "Add ownership transfer and invite actions"
```

---

## Task 8: Invitations — list mine, accept, decline

**Files:**
- Modify: `projects/views.py`, `projects/urls.py`
- Test: `projects/tests/test_invitation_api.py`

**Interfaces:**
- Consumes: `InvitationSerializer` (Task 4)
- Produces: `GET /api/invitations/`, `POST /api/invitations/{id}/accept/`, `POST /api/invitations/{id}/decline/`.

- [ ] **Step 1: Write the failing tests**

Create `projects/tests/test_invitation_api.py`:

```python
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
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `docker compose run --rm web pytest projects/tests/test_invitation_api.py -v`
Expected: FAIL — `404` on every URL, since `/api/invitations/` doesn't exist yet.

- [ ] **Step 3: Write the view and wire the URL**

In `projects/views.py`, add imports and the new viewset:

```python
from django.utils import timezone
from rest_framework import mixins
```

```python
class InvitationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = InvitationSerializer
    pagination_class = None

    def get_queryset(self):
        return Invitation.objects.filter(
            invited_user=self.request.user, status=Invitation.Status.PENDING
        ).select_related("project", "invited_by")

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        invitation = get_object_or_404(Invitation, pk=pk)
        if invitation.invited_user_id != request.user.id:
            raise PermissionDenied("You can only respond to your own invitations.")

        invitation.status = Invitation.Status.ACCEPTED
        invitation.responded_at = timezone.now()
        invitation.save()
        ProjectMembership.objects.get_or_create(
            project=invitation.project,
            user=request.user,
            defaults={"role": ProjectMembership.Role.MEMBER},
        )
        return Response(status=204)

    @action(detail=True, methods=["post"])
    def decline(self, request, pk=None):
        invitation = get_object_or_404(Invitation, pk=pk)
        if invitation.invited_user_id != request.user.id:
            raise PermissionDenied("You can only respond to your own invitations.")

        invitation.status = Invitation.Status.DECLINED
        invitation.responded_at = timezone.now()
        invitation.save()
        return Response(status=204)
```

In `projects/urls.py`:

```python
from rest_framework.routers import DefaultRouter

from .views import InvitationViewSet, ProjectViewSet

router = DefaultRouter()
router.register("projects", ProjectViewSet, basename="project")
router.register("invitations", InvitationViewSet, basename="invitation")

urlpatterns = router.urls
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `docker compose run --rm web pytest projects/tests/test_invitation_api.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add projects/views.py projects/urls.py projects/tests/test_invitation_api.py
git commit -m "Add invitation listing, accept, and decline"
```

---

## Task 9: Scope Board/Card/Comment/MyTasks to project membership

**Files:**
- Modify: `boards/models.py` (`Card`, `Comment`)
- Modify: `boards/serializers.py` (`BoardSerializer`, `CardSerializer`)
- Modify: `boards/views.py` (`BoardViewSet`, `CardViewSet`, `CommentViewSet`)
- Modify: `boards/views_me.py` (`MyTasksView`)
- Test: `boards/tests/test_project_scoping.py`

**Interfaces:**
- Consumes: `IsProjectMember` (Task 3), `projects.models.ProjectMembership`
- Produces: `Card.project` and `Comment.project` properties (read-only, mirror `Board.project`). All four views now enforce `IsProjectMember` on detail actions and filter `list`/`MyTasksView` querysets to the caller's projects.

- [ ] **Step 1: Write the failing tests**

Create `boards/tests/test_project_scoping.py`:

```python
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
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `docker compose run --rm web pytest boards/tests/test_project_scoping.py -v`
Expected: several FAIL — boards/cards from other projects are currently visible, and the "move between projects" rejection doesn't exist yet.

- [ ] **Step 3: Add the `project` properties**

In `boards/models.py`, add to `Card` (after its fields, before `class Meta`):

```python
    @property
    def project(self):
        return self.board.project
```

And to `Comment`:

```python
    @property
    def project(self):
        return self.card.board.project
```

- [ ] **Step 4: Update the serializers**

In `boards/serializers.py`, add `"project"` to `BoardSerializer.Meta.fields` and a validator:

```python
class BoardSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)

    class Meta:
        model = Board
        fields = ["id", "project", "name", "description", "created_by", "created_at", "updated_at"]

    def validate_project(self, value):
        request = self.context["request"]
        if not value.memberships.filter(user=request.user).exists():
            raise serializers.ValidationError("You must be a member of this project to create a board in it.")
        return value
```

In `CardSerializer`, add a matching validator for `board`:

```python
    def validate_board(self, value):
        request = self.context["request"]
        if not value.project.memberships.filter(user=request.user).exists():
            raise serializers.ValidationError("You must be a member of this board's project.")
        return value
```

- [ ] **Step 5: Update the views**

In `boards/views.py`, add imports:

```python
from rest_framework.permissions import IsAuthenticated

from projects.models import ProjectMembership
from projects.permissions import IsProjectMember
```

Update `BoardViewSet`:

```python
class BoardViewSet(viewsets.ModelViewSet):
    """Boards are scoped to the projects a person belongs to."""

    serializer_class = BoardSerializer
    pagination_class = None
    permission_classes = [IsAuthenticated, IsProjectMember]

    def get_queryset(self):
        qs = Board.objects.select_related("project", "created_by")
        if self.action == "list":
            qs = qs.filter(
                project_id__in=ProjectMembership.objects.filter(
                    user=self.request.user
                ).values_list("project_id", flat=True)
            )
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def update(self, request, *args, **kwargs):
        # Boards do not move between projects — same "echo-back-unchanged-is-
        # fine, a real change is rejected" rule Card already applies to
        # status/board.
        if "project" in request.data:
            board = self.get_object()
            if str(request.data["project"]) != str(board.project_id):
                raise ValidationError({"project": "Boards cannot be moved between projects."})
        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=["get"])
    def cards(self, request, pk=None):
        board = self.get_object()
        cards = board.cards.select_related("assignee", "created_by")
        return Response(CardSerializer(cards, many=True).data)
```

Update `CardViewSet` — remove the old `queryset = ...` class attribute, add `permission_classes` and `get_queryset`:

```python
class CardViewSet(viewsets.ModelViewSet):
    serializer_class = CardSerializer
    pagination_class = None
    permission_classes = [IsAuthenticated, IsProjectMember]

    def get_queryset(self):
        qs = Card.objects.select_related("board__project", "assignee", "created_by")
        if self.action == "list":
            qs = qs.filter(
                board__project_id__in=ProjectMembership.objects.filter(
                    user=self.request.user
                ).values_list("project_id", flat=True)
            )
        return qs

    # perform_create, update, move, comments are unchanged — they inherit the
    # new permission_classes automatically.
```

Update `CommentViewSet` similarly — remove the `queryset = ...` class attribute, add `permission_classes` and `get_queryset`:

```python
class CommentViewSet(mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """Deletion only — comments are created through the card's own endpoint."""

    serializer_class = CommentSerializer
    permission_classes = [IsAuthenticated, IsProjectMember]

    def get_queryset(self):
        return Comment.objects.select_related("author", "card__board__project")

    # perform_destroy is unchanged.
```

In `boards/views_me.py`:

```python
from django.db.models import F
from rest_framework.generics import ListAPIView

from projects.models import ProjectMembership

from .models import Card
from .serializers import CardSerializer


class MyTasksView(ListAPIView):
    """Everything assigned to me, in a project I still belong to, that is
    still open, soonest deadline first."""

    serializer_class = CardSerializer
    pagination_class = None

    def get_queryset(self):
        member_project_ids = ProjectMembership.objects.filter(
            user=self.request.user
        ).values_list("project_id", flat=True)
        return (
            Card.objects.filter(assignee=self.request.user, board__project_id__in=member_project_ids)
            .exclude(status=Card.Status.DONE)
            .select_related("board", "assignee", "created_by")
            .order_by(F("due_date").asc(nulls_last=True), "-priority", "id")
        )
```

- [ ] **Step 6: Run the new tests, then the full suite**

Run: `docker compose run --rm web pytest boards/tests/test_project_scoping.py -v`
Expected: 9 passed.

Run: `docker compose run --rm web pytest -v`
Expected: every test in the repo passes — this is the check that scoping didn't break any board/card/comment behavior from Tasks 1–8 or the pre-existing suite.

- [ ] **Step 7: Commit**

```bash
git add boards/ projects/tests/
git commit -m "Scope boards, cards, comments and my-tasks to project membership"
```

---

## Task 10: Documentation and final regression

**Files:**
- Modify: `docs/api.md`

**Interfaces:**
- None — documentation only.

- [ ] **Step 1: Add the Projects and Invitations sections to `docs/api.md`**

Insert a new `## Projects` section after `## Boards` (before `## Cards`), and a `## Invitations` section after `## Comments` (before `## Me`):

```markdown
## Projects
Every board and card now lives inside a project. Membership is invite-only — nobody
joins a project by any route other than accepting a pending invitation.

| Method | Path | Notes |
|---|---|---|
| GET | `/api/projects/` | projects I'm a member of |
| POST | `/api/projects/` | `{key, name, description?}`; `key` is 2–10 letters, case-insensitive on input but stored uppercase, unique across the system; creator becomes Owner |
| GET | `/api/projects/{id}/` | 403 if I'm not a member (not 404 — see below), 404 if the id doesn't exist at all |
| DELETE | `/api/projects/{id}/` | Owner only; cascades to the project's boards, cards, comments, memberships and invitations |
| GET | `/api/projects/{id}/members/` | sorted Owner, then Admin, then Member |
| DELETE | `/api/projects/{id}/members/{user_id}/` | removes a member; also doubles as "leave" when `user_id` is your own — Owner can remove anyone but themself (and cannot leave without transferring ownership first, 400 if they try), Admin can remove Members only (but can leave freely), Member can only leave |
| POST | `/api/projects/{id}/members/{user_id}/role/` | `{role: "admin"\|"member"}`; Owner only; the Owner's own role can't be changed here |
| POST | `/api/projects/{id}/transfer-ownership/` | `{user_id}`; Owner only; target must already be an Admin; the caller becomes an Admin |
| POST | `/api/projects/{id}/invite/` | `{user_id}`; Owner or Admin; 400 if already a member or already invited |

**A non-member touching a project (or its boards/cards) gets `403`, not `404`.** A
genuinely nonexistent id still 404s — existence is checked first, membership second.

Every project role is one of `owner`, `admin`, `member`. There is exactly one Owner at
all times; the Owner cannot leave a project without transferring ownership to an
existing Admin first (there is no "leave" endpoint of its own — the client models
"leave" as removing your own membership, subject to the same owner restriction as any
other removal).
```

```markdown
## Invitations
| Method | Path | Notes |
|---|---|---|
| GET | `/api/invitations/` | my own pending invitations |
| POST | `/api/invitations/{id}/accept/` | creates a Member-role membership; 403 if it isn't your invitation |
| POST | `/api/invitations/{id}/decline/` | 403 if it isn't your invitation |
```

Update the existing `## Boards` and `## Cards` sections' notes lines to reflect scoping:

Change:
```markdown
| GET | `/api/boards/` | every board; unpaginated |
```
to:
```markdown
| GET | `/api/boards/` | every board in a project I'm a member of; unpaginated |
```

Change:
```markdown
| POST | `/api/boards/` | `{name, description?}`; `description` is optional; creator is taken from the session |
```
to:
```markdown
| POST | `/api/boards/` | `{project, name, description?}`; `description` is optional; creator is taken from the session; `project` must be one I'm a member of |
```

Add a line under the Boards table's existing prose:

```markdown
**`project` cannot be changed via `PATCH`/`PUT` on `/api/boards/{id}/`** — boards do not
move between projects, mirroring the rule already in place for `status` and `board` on
cards. A `PATCH` that echoes back the board's current, unchanged `project` alongside
other real edits is accepted.
```

Change:
```markdown
| GET | `/api/cards/` | **every card in the system, unscoped by board** — not filtered to "my boards" or any board in particular |
```
to:
```markdown
| GET | `/api/cards/` | every card on a board in a project I'm a member of — not filtered to "my boards" specifically, but scoped by project membership |
```

Update the `## Me` section's `/api/me/tasks/` row:

```markdown
| GET | `/api/me/tasks/` | my open cards in a project I'm still a member of, soonest due first |
```

- [ ] **Step 2: Full regression run**

Run: `docker compose run --rm web pytest -v`
Expected: every test passes (92 pre-existing + all tests added in Tasks 1–9).

Run: `docker compose run --rm web python manage.py check`
Expected: `System check identified no issues.`

- [ ] **Step 3: Commit**

```bash
git add docs/api.md
git commit -m "Document Projects and Invitations endpoints"
```

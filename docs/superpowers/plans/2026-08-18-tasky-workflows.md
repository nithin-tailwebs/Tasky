# Workflows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the production Django/DRF backend for Tasky's Workflows feature (sub-project 3 of 13) — per-project custom work item statuses, each tagged with a `todo`/`in_progress`/`done` category, replacing the fixed 3-value `WorkItem.status` enum every project currently shares.

**Architecture:** A new `WorkItemStatus` model (global to `boards`, scoped per-`Project`) replaces the fixed `WorkItem.Status` `TextChoices`. `WorkItem.status` converts from a `CharField` to a required `ForeignKey` — a genuine, invasive schema change touching the create/move/list paths and roughly a dozen existing test files, not just an additive feature. Every project (existing and new) is seeded with 3 default statuses (To Do/`todo`, In Progress/`in_progress`, Done/`done`) so nothing about current behavior changes until a project's Owner/Admin actively customizes its list. Two defaulting mechanisms cooperate deliberately: `ProjectViewSet.perform_create` seeds explicitly (so the real UI sees 3 statuses immediately), and `WorkItem.save()` self-heals (seeds on the fly, reusing the same idempotent helper) if a work item is ever created for a project with no statuses yet — this is what keeps the ~60 existing tests that create a `WorkItem` without an explicit status working unmodified, since they create their `Project` via direct ORM calls that never reach `ProjectViewSet`.

**Tech Stack:** Django 5.2, DRF 3.16, MySQL, pytest-django. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-18-tasky-workflows-design.md` (signed off 2026-08-18; the `design/` prototype it argues from was signed off the same day)

## Global Constraints

- **Role vocabulary is `owner` / `admin` / `member`** (lowercase) — unchanged.
- **Unauthenticated request → `403`, never `401`.**
- **A non-member touching a project's statuses gets `403`, not `404`; a genuinely missing id still `404`s** — the existing `IsProjectMember` object-level pattern, reused verbatim.
- **A guard-type `400` with no single offending field uses `{"detail": "..."}`** — the established convention from `projects/views.py` (`remove_member`/`transfer_ownership`) and sub-project 2b.
- **Client-controlled input reaching a raw cast or ORM lookup must be validated first, not left to raise an uncaught exception.** Sub-project 2b shipped this exact bug three separate times (an unguarded `int()` in two different `_reposition` methods, an unguarded `Screen.objects.filter(pk=screen_id)`) before it was fixed each time in a review round. Every new endpoint in this plan validates the type of a client-supplied id *before* it reaches a `.filter(pk=...)`/`int()`/`float()` call.
- **`item.status_id`, never `item.status`, for raw-id comparisons.** `WorkItemViewSet.update()`'s existing immutability check already does this correctly for `board` (`str(request.data["board"]) != str(item.board_id)`) — once `status` becomes a `ForeignKey`, its equivalent check must use `item.status_id` the same way. Comparing `request.data["status"]` (a string from JSON) against `item.status` (a model instance, once accessed) is a real bug — they are never equal, so every PATCH naming `status` — even one just echoing back the current value — would be wrongly rejected.
- **Migrations that change existing data need the multi-step pattern already established in this codebase** (`boards/migrations/0009`–`0011` for `WorkItem.key`): add the new shape alongside the old, backfill with a `RunPython` data migration using `apps.get_model(...)` historical models (never the real imported model), then remove the old shape. `WorkItem.status`'s conversion from `CharField` to `ForeignKey` follows this exactly, across Tasks 1 and 2.

---

## Task 1: `WorkItemStatus` model, backfill, and CRUD endpoints

**Files:**
- Create: `boards/migrations/0018_work_item_status.py`, `boards/migrations/0019_backfill_work_item_statuses.py`
- Modify: `boards/models.py`, `boards/services.py`, `boards/serializers.py`, `boards/views.py`, `boards/urls.py`, `boards/admin.py`, `projects/views.py`
- Test: `boards/tests/test_work_item_statuses_api.py`

**Interfaces:**
- Consumes: `IsProjectMember`, `can_manage_components`-tier role check pattern (a new `can_manage_statuses(role)` mirrors it exactly), the `_reposition` idiom from 2b's `FieldOptionViewSet`/`ScreenFieldViewSet`.
- Produces: `boards.models.WorkItemStatus` (`project`, `name`, `category`, `position`; unique together on `(project, name)`). `boards.services.seed_default_statuses(project) -> dict[str, WorkItemStatus]` — **idempotent**: returns the project's existing 3 default-category statuses if any already exist, only creates them the first time. `boards.services.resolve_default_status(project) -> WorkItemStatus` — the lowest-position `todo`-category status. `WorkItemStatusSerializer`. `GET/POST /api/projects/{id}/statuses/`, `PATCH/DELETE /api/projects/{id}/statuses/{id}/`. Task 2 imports `seed_default_statuses`/`resolve_default_status` and the model.

- [ ] **Step 1: Write the failing tests**

Create `boards/tests/test_work_item_statuses_api.py`:

```python
import pytest

from boards.models import WorkItemStatus
from boards.services import seed_default_statuses


@pytest.mark.django_db
def test_anonymous_callers_are_rejected(client, project):
    assert client.get(f"/api/projects/{project.id}/statuses/").status_code == 403


@pytest.mark.django_db
def test_a_non_member_cannot_view_statuses(auth_client, other_user):
    from projects.models import Project, ProjectMembership

    foreign = Project.objects.create(key="FOREIGN", name="Not Yours")
    ProjectMembership.objects.create(project=foreign, user=other_user, role="owner")

    assert auth_client.get(f"/api/projects/{foreign.id}/statuses/").status_code == 403


@pytest.mark.django_db
def test_a_fresh_project_created_through_the_api_has_3_default_statuses(auth_client):
    response = auth_client.post(
        "/api/projects/", {"key": "FRESH", "name": "Fresh Project"}, content_type="application/json"
    )
    assert response.status_code == 201
    project_id = response.json()["id"]

    listed = auth_client.get(f"/api/projects/{project_id}/statuses/")
    names_and_categories = sorted(
        (s["name"], s["category"]) for s in listed.json()
    )
    assert names_and_categories == [
        ("Done", "done"), ("In Progress", "in_progress"), ("To Do", "todo"),
    ]


@pytest.mark.django_db
def test_seed_default_statuses_is_idempotent(project):
    first = seed_default_statuses(project)
    second = seed_default_statuses(project)
    assert first["todo"].id == second["todo"].id
    assert WorkItemStatus.objects.filter(project=project).count() == 3


@pytest.mark.django_db
def test_owner_can_add_a_custom_status(auth_client, project):
    seed_default_statuses(project)
    response = auth_client.post(
        f"/api/projects/{project.id}/statuses/",
        {"name": "Blocked", "category": "in_progress"},
        content_type="application/json",
    )
    assert response.status_code == 201
    status = WorkItemStatus.objects.get(project=project, name="Blocked")
    assert status.category == "in_progress"
    assert status.position == 3


@pytest.mark.django_db
def test_a_plain_member_cannot_add_a_status(auth_client, project):
    from projects.models import ProjectMembership

    seed_default_statuses(project)
    ProjectMembership.objects.filter(project=project, user__username="alice").update(role="member")
    response = auth_client.post(
        f"/api/projects/{project.id}/statuses/",
        {"name": "Blocked", "category": "in_progress"},
        content_type="application/json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_duplicate_status_name_in_the_same_project_is_rejected(auth_client, project):
    statuses = seed_default_statuses(project)
    response = auth_client.post(
        f"/api/projects/{project.id}/statuses/",
        {"name": "to do", "category": "todo"},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert WorkItemStatus.objects.filter(project=project).count() == 3


@pytest.mark.django_db
def test_owner_can_rename_a_status(auth_client, project):
    statuses = seed_default_statuses(project)
    response = auth_client.patch(
        f"/api/projects/{project.id}/statuses/{statuses['todo'].id}/",
        {"name": "Backlog"},
        content_type="application/json",
    )
    assert response.status_code == 200
    statuses["todo"].refresh_from_db()
    assert statuses["todo"].name == "Backlog"


@pytest.mark.django_db
def test_recategorizing_a_status_is_rejected_if_it_would_empty_a_category(auth_client, project):
    statuses = seed_default_statuses(project)
    response = auth_client.patch(
        f"/api/projects/{project.id}/statuses/{statuses['done'].id}/",
        {"category": "in_progress"},
        content_type="application/json",
    )
    assert response.status_code == 400
    statuses["done"].refresh_from_db()
    assert statuses["done"].category == "done"


@pytest.mark.django_db
def test_recategorizing_a_status_succeeds_when_another_remains_in_its_old_category(auth_client, project):
    statuses = seed_default_statuses(project)
    extra = WorkItemStatus.objects.create(project=project, name="Also Done", category="done", position=3)

    response = auth_client.patch(
        f"/api/projects/{project.id}/statuses/{statuses['done'].id}/",
        {"category": "in_progress"},
        content_type="application/json",
    )
    assert response.status_code == 200
    statuses["done"].refresh_from_db()
    assert statuses["done"].category == "in_progress"


@pytest.mark.django_db
def test_reordering_a_status(auth_client, project):
    statuses = seed_default_statuses(project)
    response = auth_client.patch(
        f"/api/projects/{project.id}/statuses/{statuses['done'].id}/",
        {"position": 0},
        content_type="application/json",
    )
    assert response.status_code == 200
    statuses["todo"].refresh_from_db()
    statuses["done"].refresh_from_db()
    assert statuses["done"].position == 0
    assert statuses["todo"].position == 1


@pytest.mark.django_db
def test_reordering_with_a_non_numeric_position_is_rejected(auth_client, project):
    statuses = seed_default_statuses(project)
    response = auth_client.patch(
        f"/api/projects/{project.id}/statuses/{statuses['todo'].id}/",
        {"position": "not-a-number"},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "position" in response.json()


@pytest.mark.django_db
def test_deleting_an_unused_status_succeeds(auth_client, project):
    statuses = seed_default_statuses(project)
    extra = WorkItemStatus.objects.create(project=project, name="Blocked", category="in_progress", position=3)

    response = auth_client.delete(f"/api/projects/{project.id}/statuses/{extra.id}/")
    assert response.status_code == 204


@pytest.mark.django_db
def test_deleting_the_last_status_in_a_category_is_rejected(auth_client, project):
    statuses = seed_default_statuses(project)
    response = auth_client.delete(f"/api/projects/{project.id}/statuses/{statuses['done'].id}/")
    assert response.status_code == 400
    assert WorkItemStatus.objects.filter(id=statuses["done"].id).exists()


@pytest.mark.django_db
def test_statuses_are_scoped_per_project(auth_client, project, user):
    from projects.models import Project, ProjectMembership

    other_project = Project.objects.create(key="OTHER", name="Elsewhere")
    ProjectMembership.objects.create(project=other_project, user=user, role="owner")
    seed_default_statuses(project)
    seed_default_statuses(other_project)

    response = auth_client.get(f"/api/projects/{project.id}/statuses/")
    assert len(response.json()) == 3
    names = {s["name"] for s in response.json()}
    assert names == {"To Do", "In Progress", "Done"}
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `docker compose run --rm web pytest boards/tests/test_work_item_statuses_api.py -v`
Expected: FAIL — `ImportError` (`WorkItemStatus` doesn't exist yet).

- [ ] **Step 3: Add the model**

In `boards/models.py`, add after the `Component` class (before `CustomField`, since alphabetical/dependency order doesn't matter to Python but keeping the "core work item structure" models together aids readability):

```python
class WorkItemStatus(models.Model):
    class Category(models.TextChoices):
        TODO = "todo", "To Do"
        IN_PROGRESS = "in_progress", "In Progress"
        DONE = "done", "Done"

    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="statuses")
    name = models.CharField(max_length=80)
    category = models.CharField(max_length=20, choices=Category.choices)
    position = models.IntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(fields=["project", "name"], name="unique_status_name_per_project"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.project})"
```

```bash
docker compose run --rm web python manage.py makemigrations boards -n work_item_status
```

Confirm the generated file is `boards/migrations/0018_work_item_status.py`.

- [ ] **Step 4: Write the backfill data migration**

Create `boards/migrations/0019_backfill_work_item_statuses.py`:

```python
from django.db import migrations

DEFAULTS = [("To Do", "todo", 0), ("In Progress", "in_progress", 1), ("Done", "done", 2)]


def seed_existing_projects(apps, schema_editor):
    Project = apps.get_model("projects", "Project")
    WorkItemStatus = apps.get_model("boards", "WorkItemStatus")

    for project in Project.objects.all():
        if WorkItemStatus.objects.filter(project=project).exists():
            continue
        WorkItemStatus.objects.bulk_create(
            WorkItemStatus(project=project, name=name, category=category, position=position)
            for name, category, position in DEFAULTS
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("boards", "0018_work_item_status"),
        ("projects", "0002_project_next_item_number"),
    ]
    operations = [
        migrations.RunPython(seed_existing_projects, noop_reverse),
    ]
```

- [ ] **Step 5: Add `seed_default_statuses` and `resolve_default_status` to `boards/services.py`**

Add to the top-level import: `from .models import ..., WorkItemStatus` (append to the existing `from .models import` line). Add, near the top of the file (after the imports, before `next_position`):

```python
_DEFAULT_STATUSES = [("To Do", "todo", 0), ("In Progress", "in_progress", 1), ("Done", "done", 2)]


def seed_default_statuses(project) -> dict:
    """The 3 default statuses every project starts with. Idempotent: if the
    project already has any statuses (from an earlier call, or because it
    was seeded some other way), returns its existing todo/in_progress/done
    rows instead of creating duplicates.

    Reached two ways, deliberately: called explicitly from
    ProjectViewSet.perform_create (so a project created through the real API
    has 3 statuses immediately), and reached indirectly — via
    resolve_default_status()'s own fallback, below — from WorkItem.save()
    (so a project created directly via the ORM — every existing test
    fixture, seed_demo, etc. — still works without being rewritten to seed
    anything itself)."""
    existing = {s.category: s for s in WorkItemStatus.objects.filter(project=project)}
    if existing:
        # Whatever exists, return a dict good enough for resolve_default_status
        # to work with — a project that already has custom statuses is not
        # re-seeded, only reported back.
        return existing

    created = [
        WorkItemStatus(project=project, name=name, category=category, position=position)
        for name, category, position in _DEFAULT_STATUSES
    ]
    WorkItemStatus.objects.bulk_create(created)
    return {status.category: status for status in created}


def resolve_default_status(project):
    """The status a new work item lands in when none is given — the
    lowest-position todo-category status, i.e. the leftmost column.
    Seeds the project's defaults first if it has none at all yet."""
    status = (
        WorkItemStatus.objects.filter(project=project, category=WorkItemStatus.Category.TODO)
        .order_by("position", "id")
        .first()
    )
    if status is not None:
        return status
    return seed_default_statuses(project)["todo"]
```

- [ ] **Step 6: Add the permission helper and serializer**

In `boards/serializers.py`, add next to `can_manage_components`:

```python
def can_manage_statuses(role):
    return role in ("owner", "admin")
```

Update the `from .models import ...` line to include `WorkItemStatus`. Add, after `ComponentSerializer`:

```python
class WorkItemStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkItemStatus
        fields = ["id", "project", "name", "category", "position"]
        read_only_fields = ["project", "position"]

    def validate_name(self, value):
        clean = value.strip()
        if not clean:
            raise serializers.ValidationError("This field may not be blank.")
        return clean
```

(Uniqueness is checked in the view, the same way `ComponentViewSet` checks it — `project` is a read-only field here too, so DRF's automatic `UniqueTogetherValidator` never gets built for the same reason documented on `ComponentViewSet.perform_create`.)

- [ ] **Step 7: Add the viewset**

In `boards/views.py`, update the `from .models import ...` line to include `WorkItemStatus`, the `.serializers import (...)` block to include `WorkItemStatusSerializer, can_manage_statuses`. Add, after `ComponentViewSet`:

```python
class WorkItemStatusViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = WorkItemStatusSerializer
    permission_classes = [IsAuthenticated, IsProjectMember]
    pagination_class = None

    def get_project(self):
        from projects.models import Project

        return get_object_or_404(Project, pk=self.kwargs["project_pk"])

    def get_queryset(self):
        return WorkItemStatus.objects.filter(project_id=self.kwargs["project_pk"])

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if self.action in ("list", "create"):
            self.check_object_permissions(request, self.get_project())

    def perform_create(self, serializer):
        project = self.get_project()
        role = project.memberships.get(user=self.request.user).role
        if not can_manage_statuses(role):
            raise PermissionDenied("You don't have permission to manage this project's statuses.")
        name = serializer.validated_data.get("name")
        if WorkItemStatus.objects.filter(project=project, name__iexact=name).exists():
            raise ValidationError({"name": f'"{name}" already exists.'})
        position = WorkItemStatus.objects.filter(project=project).count()
        serializer.save(project=project, position=position)

    def perform_update(self, serializer):
        instance = serializer.instance
        role = instance.project.memberships.get(user=self.request.user).role
        if not can_manage_statuses(role):
            raise PermissionDenied("You don't have permission to manage this project's statuses.")

        name = serializer.validated_data.get("name")
        if name and WorkItemStatus.objects.filter(
            project=instance.project, name__iexact=name
        ).exclude(pk=instance.pk).exists():
            raise ValidationError({"name": f'"{name}" already exists.'})

        new_category = serializer.validated_data.get("category")
        if new_category and new_category != instance.category:
            remaining = WorkItemStatus.objects.filter(
                project=instance.project, category=instance.category
            ).exclude(pk=instance.pk)
            if not remaining.exists():
                raise ValidationError(
                    {"category": f"{instance.get_category_display()} needs at least one status — recategorize another one first."}
                )

        serializer.save()
        if "position" in self.request.data:
            self._reposition(instance)

    def _reposition(self, instance):
        try:
            target = max(0, int(self.request.data["position"]))
        except (TypeError, ValueError):
            raise ValidationError({"position": "Must be a whole number."})
        siblings = list(
            WorkItemStatus.objects.filter(project=instance.project)
            .exclude(pk=instance.pk)
            .order_by("position", "id")
        )
        target = min(target, len(siblings))
        siblings.insert(target, instance)
        for index, status in enumerate(siblings):
            if status.position != index:
                status.position = index
                status.save(update_fields=["position"])

    def perform_destroy(self, instance):
        # No "still in use by a work item" guard yet — WorkItem.status is
        # still a plain CharField at this point in the plan (Task 2 converts
        # it to a ForeignKey to WorkItemStatus), so there is no relationship
        # to query here at all. Task 2 replaces this method with the real
        # guard once that FK — and the reverse accessor it creates — exists.
        # This mirrors sub-project 2b's CustomField/Screen/FieldOption
        # delete guards, each of which shipped unguarded in the task that
        # introduced the model and gained its real guard in a later task
        # once the model it needed to check against existed.
        role = instance.project.memberships.get(user=self.request.user).role
        if not can_manage_statuses(role):
            raise PermissionDenied("You don't have permission to manage this project's statuses.")

        remaining = WorkItemStatus.objects.filter(
            project=instance.project, category=instance.category
        ).exclude(pk=instance.pk)
        if not remaining.exists():
            raise ValidationError({"detail": f"{instance.get_category_display()} needs at least one status."})

        project = instance.project
        instance.delete()
        siblings = list(WorkItemStatus.objects.filter(project=project).order_by("position", "id"))
        for index, status in enumerate(siblings):
            if status.position != index:
                status.position = index
                status.save(update_fields=["position"])
```

- [ ] **Step 8: Wire the URL**

In `boards/urls.py`, update the import to include `WorkItemStatusViewSet`, and add (alongside the existing `projects/<int:project_pk>/components/` paths):

```python
    path(
        "projects/<int:project_pk>/statuses/",
        WorkItemStatusViewSet.as_view({"get": "list", "post": "create"}),
        name="project-statuses",
    ),
    path(
        "projects/<int:project_pk>/statuses/<int:pk>/",
        WorkItemStatusViewSet.as_view({"patch": "partial_update", "delete": "destroy"}),
        name="project-status-detail",
    ),
```

- [ ] **Step 9: Seed default statuses on project creation**

In `projects/views.py`, in `ProjectViewSet.perform_create`, add the explicit seed call after the membership is created:

```python
    def perform_create(self, serializer):
        project = serializer.save()
        ProjectMembership.objects.create(
            project=project, user=self.request.user, role=ProjectMembership.Role.OWNER
        )
        from boards.services import seed_default_statuses

        seed_default_statuses(project)
```

(Local import, matching the established cross-app-boundary pattern already used throughout `boards/views.py` for `from projects.models import Project` inside individual methods — `projects` importing from `boards` is the reverse direction from what's been done before in this codebase, which is exactly why it's kept local to this one function rather than a top-level import: it avoids asserting a new module-load-time dependency between the two apps for the sake of one call site.)

- [ ] **Step 10: Register in admin**

In `boards/admin.py`, update the `from .models import ...` line to include `WorkItemStatus`, and add:

```python
@admin.register(WorkItemStatus)
class WorkItemStatusAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "project", "position"]
    list_filter = ["category"]
    search_fields = ["name"]
```

- [ ] **Step 11: Run the tests to confirm they pass**

Run: `docker compose run --rm web pytest boards/tests/test_work_item_statuses_api.py -v`
Expected: 15 passed.

Run: `docker compose run --rm web pytest -v`
Expected: all tests pass (284 total — 269 baseline + 15 new; nothing else in the existing suite is touched by this task, since `WorkItem.status` itself doesn't change until Task 2).

- [ ] **Step 12: Commit**

```bash
git add boards/ projects/views.py
git commit -m "Add WorkItemStatus model, per-project CRUD, and default seeding"
```

---

## Task 2: Convert `WorkItem.status` to a `WorkItemStatus` foreign key

**This is the breaking task.** Everything in Task 1 is purely additive; this task changes an existing required field's type and therefore touches every place that reads or writes `WorkItem.status`, including roughly a dozen existing tests that predate this feature.

**Files:**
- Create: `boards/migrations/0020_workitem_new_status.py`, `boards/migrations/0021_backfill_workitem_new_status.py`, `boards/migrations/0022_workitem_status_required.py`
- Modify: `boards/models.py`, `boards/services.py`, `boards/serializers.py`, `boards/views.py`, `boards/views_me.py`, `boards/management/commands/seed_demo.py`
- Modify (repairing pre-existing tests broken by this field-type change): `boards/tests/test_work_item_api.py`, `boards/tests/test_work_item_model.py`, `boards/tests/test_work_item_move.py`, `boards/tests/test_my_tasks.py`, `boards/tests/test_seed_demo.py`
- Test (new coverage for this task specifically): `boards/tests/test_work_item_status_wiring.py`

**Interfaces:**
- Consumes: `WorkItemStatus`, `seed_default_statuses`, `resolve_default_status` (Task 1).
- Produces: `WorkItem.status` (FK, `on_delete=PROTECT`, `related_name="work_items_with_status"`). Also replaces Task 1's deliberately unguarded `WorkItemStatusViewSet.perform_destroy` with the real "still in use by a work item" guard, now that this FK — and the `work_items_with_status` reverse accessor it creates — exists. `WorkItemSerializer.status` (write: id: int; read via `status_detail`). `WorkItemStatusSummarySerializer` (`id`, `name`, `category`) used for `status_detail` and updates `WorkItemSummarySerializer`'s `status` field the same way.

- [ ] **Step 1: Write the failing tests for the new behavior this task adds**

Create `boards/tests/test_work_item_status_wiring.py`:

```python
import pytest

from boards.models import Board, WorkItem, WorkItemStatus
from boards.services import seed_default_statuses


@pytest.fixture
def board(user, project):
    return Board.objects.create(name="Test Board", created_by=user, project=project)


@pytest.mark.django_db
def test_a_new_work_item_defaults_to_the_todo_status(auth_client, board, project):
    seed_default_statuses(project)
    response = auth_client.post(
        "/api/work-items/", {"board": board.id, "title": "X"}, content_type="application/json"
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status_detail"]["category"] == "todo"
    assert body["status_detail"]["name"] == "To Do"


@pytest.mark.django_db
def test_creating_a_work_item_with_an_explicit_status_still_works(auth_client, board, project):
    statuses = seed_default_statuses(project)
    response = auth_client.post(
        "/api/work-items/",
        {"board": board.id, "title": "Started already", "status": statuses["in_progress"].id},
        content_type="application/json",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == statuses["in_progress"].id
    assert body["status_detail"]["name"] == "In Progress"


@pytest.mark.django_db
def test_a_work_item_created_for_a_project_with_no_statuses_yet_self_heals(auth_client, user):
    """Direct-ORM project creation (every test fixture, seed_demo, the admin)
    never calls ProjectViewSet.perform_create, so it never explicitly seeds
    default statuses. WorkItem.save() must seed them on the fly the first
    time a work item actually needs one — this is what keeps the rest of
    this codebase's existing tests working unmodified."""
    from projects.models import Project, ProjectMembership

    fresh_project = Project.objects.create(key="FRESH", name="Fresh")
    ProjectMembership.objects.create(project=fresh_project, user=user, role="owner")
    fresh_board = Board.objects.create(name="B", created_by=user, project=fresh_project)
    assert WorkItemStatus.objects.filter(project=fresh_project).count() == 0

    item = WorkItem.objects.create(board=fresh_board, title="First ever item")

    assert WorkItemStatus.objects.filter(project=fresh_project).count() == 3
    assert item.status.category == "todo"


@pytest.mark.django_db
def test_assigning_a_status_from_another_project_is_rejected(auth_client, board, project, user):
    from projects.models import Project, ProjectMembership

    other_project = Project.objects.create(key="OTHER", name="Elsewhere")
    ProjectMembership.objects.create(project=other_project, user=user, role="owner")
    other_statuses = seed_default_statuses(other_project)

    response = auth_client.post(
        "/api/work-items/",
        {"board": board.id, "title": "X", "status": other_statuses["todo"].id},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "status" in response.json()


@pytest.mark.django_db
def test_move_rejects_a_status_from_another_project(auth_client, board, project, user):
    from projects.models import Project, ProjectMembership

    seed_default_statuses(project)
    item = WorkItem.objects.create(board=board, title="X")
    other_project = Project.objects.create(key="OTHER", name="Elsewhere")
    ProjectMembership.objects.create(project=other_project, user=user, role="owner")
    other_statuses = seed_default_statuses(other_project)

    response = auth_client.post(
        f"/api/work-items/{item.id}/move/",
        {"status": other_statuses["done"].id, "position": 0},
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_my_tasks_excludes_every_status_in_the_done_category(auth_client, board, project, user):
    statuses = seed_default_statuses(project)
    extra_done = WorkItemStatus.objects.create(project=project, name="Archived", category="done", position=3)

    WorkItem.objects.create(board=board, title="Still going", assignee=user, status=statuses["todo"])
    WorkItem.objects.create(board=board, title="Finished", assignee=user, status=statuses["done"])
    WorkItem.objects.create(board=board, title="Also finished", assignee=user, status=extra_done)

    response = auth_client.get("/api/me/tasks/")
    assert [item["title"] for item in response.json()] == ["Still going"]


@pytest.mark.django_db
def test_patching_status_directly_is_still_rejected(auth_client, board, project):
    statuses = seed_default_statuses(project)
    item = WorkItem.objects.create(board=board, title="Untouched", status=statuses["todo"])

    response = auth_client.patch(
        f"/api/work-items/{item.id}/",
        {"status": statuses["done"].id},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "status" in response.json()
    item.refresh_from_db()
    assert item.status_id == statuses["todo"].id


@pytest.mark.django_db
def test_patching_with_status_echoed_back_unchanged_still_updates_other_fields(auth_client, board, project):
    """The bug this task's Global Constraints section calls out by name:
    item.status (once accessed) is a WorkItemStatus instance, never equal
    to the raw id string PATCHed back — the immutability check must compare
    against item.status_id instead, or every echo-back would 400."""
    statuses = seed_default_statuses(project)
    item = WorkItem.objects.create(board=board, title="Before", status=statuses["todo"])

    response = auth_client.patch(
        f"/api/work-items/{item.id}/",
        {"status": statuses["todo"].id, "title": "After"},
        content_type="application/json",
    )
    assert response.status_code == 200
    item.refresh_from_db()
    assert item.title == "After"
    assert item.status_id == statuses["todo"].id


@pytest.mark.django_db
def test_deleting_a_status_still_used_by_a_work_item_is_rejected(auth_client, board, project):
    """The real guard on WorkItemStatusViewSet.perform_destroy, now that
    WorkItem.status is a real FK — Task 1 left this endpoint unguarded
    since WorkItem didn't reference WorkItemStatus yet at that point."""
    statuses = seed_default_statuses(project)
    WorkItem.objects.create(board=board, title="Uses it", status=statuses["todo"])

    response = auth_client.delete(f"/api/projects/{project.id}/statuses/{statuses['todo'].id}/")
    assert response.status_code == 400
    assert WorkItemStatus.objects.filter(id=statuses["todo"].id).exists()
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `docker compose run --rm web pytest boards/tests/test_work_item_status_wiring.py -v`
Expected: FAIL — `WorkItem.objects.create(..., status=statuses["todo"])` raises `ValueError` (`status` is still a plain `CharField`, doesn't accept a `WorkItemStatus` instance) or the seed data hasn't run self-healing yet. The whole file should fail to collect or fail immediately.

- [ ] **Step 3: Add the new field alongside the old one**

In `boards/models.py`, add to `WorkItem` (after the existing `status` field, temporarily — it will be removed in Step 6):

```python
    new_status = models.ForeignKey(
        "WorkItemStatus", on_delete=models.PROTECT, null=True, blank=True,
        related_name="work_items_with_status",
    )
```

```bash
docker compose run --rm web python manage.py makemigrations boards -n workitem_new_status
```

Confirm the generated file is `boards/migrations/0020_workitem_new_status.py`.

- [ ] **Step 4: Write the backfill data migration**

Create `boards/migrations/0021_backfill_workitem_new_status.py`:

```python
from django.db import migrations


def backfill_new_status(apps, schema_editor):
    WorkItem = apps.get_model("boards", "WorkItem")
    WorkItemStatus = apps.get_model("boards", "WorkItemStatus")

    # Every project already has exactly one status per category at this
    # point (Task 1's 0019 backfill guarantees it, and no project can have
    # picked up a second same-category status yet — the API this migration
    # predates hasn't shipped), so matching on (project, category) is
    # unambiguous here even though it would not be once customization exists.
    #
    # Collected into a list up front, not re-queried inside bulk_update:
    # bulk_update() takes the exact Python objects you pass it and writes
    # whatever attributes are currently set on them — it never re-fetches.
    # Building a fresh queryset there instead of reusing `items` would hand
    # bulk_update a set of objects that never had new_status_id set at all.
    items = list(WorkItem.objects.select_related("board").all())
    for item in items:
        status = WorkItemStatus.objects.get(
            project_id=item.board.project_id, category=item.status
        )
        item.new_status_id = status.id
    WorkItem.objects.bulk_update(items, ["new_status_id"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("boards", "0020_workitem_new_status"),
        ("boards", "0019_backfill_work_item_statuses"),
    ]
    operations = [
        migrations.RunPython(backfill_new_status, noop_reverse),
    ]
```

- [ ] **Step 5: Run migrations and confirm the backfill worked**

```bash
docker compose run --rm web python manage.py migrate boards
docker compose run --rm web python manage.py shell -c "
from boards.models import WorkItem
print(WorkItem.objects.filter(new_status__isnull=True).count())
"
```
Expected: `0` — every existing `WorkItem` now has a `new_status`.

- [ ] **Step 6: Remove the old field, rename the new one, make it required**

In `boards/models.py`:
- Remove the old `status = models.CharField(...)` field and the `class Status(models.TextChoices): ...` inner class entirely from `WorkItem`.
- Rename `new_status` to `status`, remove `null=True, blank=True`.
- Keep `on_delete=models.PROTECT` and `related_name="work_items_with_status"`.

Result:

```python
    status = models.ForeignKey(
        "WorkItemStatus", on_delete=models.PROTECT, related_name="work_items_with_status",
    )
```

(`WorkItemStatus` is defined earlier in the same file per Task 1, so the plain string forward-reference `"WorkItemStatus"` isn't strictly required — either form works; keep the string form for consistency with how `parent = models.ForeignKey("self", ...)` and `components = models.ManyToManyField("Component", ...)` are already written elsewhere in this same model.)

```bash
docker compose run --rm web python manage.py makemigrations boards -n workitem_status_required
```

Confirm the generated file is `boards/migrations/0022_workitem_status_required.py` and that it contains a `RemoveField("status")`, a `RenameField("new_status", "status")`, and an `AlterField` dropping `null=True`. If `makemigrations` produces something different (e.g. it doesn't detect the rename and instead offers to add a new field), answer its interactive prompts to select "rename" rather than "add new" — the field's the same underlying data, a genuine rename, not a fresh column.

- [ ] **Step 7: Update `WorkItem.save()` with the self-healing fallback**

In `boards/models.py`, `WorkItem.save()` currently only special-cases `key` generation. Extend it to also resolve a missing `status` under the same lock (reusing the existing `select_for_update()` on `Project`, which already serializes concurrent first-writes for one project):

```python
    def save(self, *args, **kwargs):
        if not self.key or not self.status_id:
            from projects.models import Project

            with transaction.atomic():
                project = Project.objects.select_for_update().get(pk=self.board.project_id)
                if not self.status_id:
                    from .services import resolve_default_status

                    self.status = resolve_default_status(project)
                if not self.key:
                    self.key = f"{project.key}-{project.next_item_number}"
                    project.next_item_number += 1
                    project.save(update_fields=["next_item_number"])
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)
```

Update the docstring-style comment above this method (currently only discusses `key`) to note the same lock now also guards status defaulting — the reasoning ("a duplicate is a real correctness bug, hence the real lock, not the lock-free `next_position` pattern") applies identically to seeding a project's first-ever statuses, which must not double-create under concurrent first writes.

- [ ] **Step 8: Update `boards/services.py`'s `next_position` and `move_work_item`**

Change `next_position`'s signature and body to take a status id instead of a status string:

```python
def next_position(board_id: int, status_id: int) -> int:
    """The position a new work item takes: the end of its column.
    ... (docstring unchanged otherwise — the concurrency reasoning is identical) ...
    """
    highest = WorkItem.objects.filter(board_id=board_id, status_id=status_id).aggregate(
        highest=Max("position")
    )["highest"]
    return 0 if highest is None else highest + 1
```

Rewrite `move_work_item` to compare `status_id` throughout, never `status` (which would trigger a DB fetch per comparison — the exact N+1 pattern already fixed once in `custom_fields_read_map`, avoided here from the start):

```python
@transaction.atomic
def move_work_item(item: WorkItem, new_status_id: int, new_position: int) -> WorkItem:
    """... (docstring unchanged — the locking/renumbering reasoning is
    identical; only the field being compared changes from a string to an id) ..."""
    locked = list(
        WorkItem.objects.select_for_update()
        .filter(board_id=item.board_id)
        .order_by("id")
    )

    locked_by_pk = {c.pk: c for c in locked}
    if item.pk not in locked_by_pk:
        raise WorkItem.DoesNotExist(
            f"WorkItem {item.pk} was deleted before the move could be applied."
        )

    old_status_id = locked_by_pk[item.pk].status_id
    item.status_id = new_status_id

    def renumber(status_id: int) -> list[WorkItem]:
        column = [c for c in locked if c.status_id == status_id and c.pk != item.pk]
        column.sort(key=lambda c: (c.position, c.pk))

        if status_id == new_status_id:
            index = max(0, min(new_position, len(column)))
            column.insert(index, item)

        now = timezone.now()
        for index, member in enumerate(column):
            member.position = index
            member.updated_at = now
        return column

    touched = renumber(new_status_id)
    if old_status_id != new_status_id:
        touched += renumber(old_status_id)

    WorkItem.objects.bulk_update(touched, ["position", "status", "updated_at"])
    return item
```

(`bulk_update`'s field list keeps `"status"`, not `"status_id"` — Django's `bulk_update` takes model field names, and translates a `ForeignKey` field name to its underlying `_id` column automatically, reading whichever of `.status`/`.status_id` was last set on each object; since this function only ever sets `.status_id`, that's what gets written.)

- [ ] **Step 9: Update `boards/serializers.py`**

Update the `from .models import ...` line to include `WorkItemStatus`. Update the `from .services import ...` line to include `resolve_default_status`. Add, after `WorkItemSummarySerializer`'s current definition — replace it entirely (it needs a resolved status now, not a bare id, for the same reason `parent_detail` exists):

```python
class WorkItemStatusSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkItemStatus
        fields = ["id", "name", "category"]


class WorkItemSummarySerializer(serializers.ModelSerializer):
    """Enough to identify and link to another work item, without pulling
    its full field set — used for parent_detail and the children list."""

    status_detail = WorkItemStatusSummarySerializer(source="status", read_only=True)

    class Meta:
        model = WorkItem
        fields = ["id", "key", "title", "item_type", "status", "status_detail"]
```

Update `WorkItemSerializer`: add `status_detail`, make `status` explicitly not required (no static default is possible, per Global Constraints), and add project-match + default-injection logic to `validate()`:

```python
class WorkItemSerializer(serializers.ModelSerializer):
    assignee_detail = UserSerializer(source="assignee", read_only=True)
    created_by = UserSerializer(read_only=True)
    priority_label = serializers.CharField(source="get_priority_display", read_only=True)
    parent_detail = WorkItemSummarySerializer(source="parent", read_only=True)
    components_detail = ComponentSerializer(source="components", many=True, read_only=True)
    status_detail = WorkItemStatusSummarySerializer(source="status", read_only=True)
    status = serializers.PrimaryKeyRelatedField(queryset=WorkItemStatus.objects.all(), required=False)
    custom_fields = serializers.DictField(required=False, write_only=True)

    class Meta:
        model = WorkItem
        fields = [
            "id", "key", "board", "item_type", "title", "description",
            "status", "status_detail", "priority", "priority_label", "due_date",
            "assignee", "assignee_detail", "parent", "parent_detail",
            "components", "components_detail", "custom_fields",
            "position", "created_by", "created_at", "updated_at",
        ]
        read_only_fields = ["key", "position"]

    def validate_board(self, value):
        request = self.context["request"]
        if not value.project.memberships.filter(user=request.user).exists():
            raise serializers.ValidationError("You must be a member of this board's project.")
        return value

    def validate(self, attrs):
        is_create = self.instance is None
        parent_touched = is_create or "parent" in attrs

        if parent_touched:
            item_type = attrs.get("item_type") or (
                self.instance.item_type if self.instance else WorkItem.ItemType.TASK
            )
            parent = attrs.get("parent")
            board = attrs.get("board") or (self.instance.board if self.instance else None)

            if parent is not None:
                if board is not None and parent.board_id != board.id:
                    raise serializers.ValidationError({"parent": "Parent must be on the same board."})
                if not is_create and parent.id == self.instance.id:
                    raise serializers.ValidationError({"parent": "An item can't be its own parent."})

            error = hierarchy_error(item_type, parent)
            if error:
                raise serializers.ValidationError({"parent": error})

        if "components" in attrs:
            board = attrs.get("board") or (self.instance.board if self.instance else None)
            mismatched = [c for c in attrs["components"] if c.project_id != board.project_id]
            if mismatched:
                raise serializers.ValidationError(
                    {"components": "Components must belong to this item's project."}
                )

        board = attrs.get("board") or (self.instance.board if self.instance else None)
        if "status" in attrs:
            if attrs["status"].project_id != board.project_id:
                raise serializers.ValidationError({"status": "Status must belong to this item's project."})
        elif is_create:
            # No static model-level default is possible (the right default
            # depends on which project this item's board belongs to), so
            # inject a real one here rather than leaving it to WorkItem.save()'s
            # lazy fallback — perform_create needs the resolved status BEFORE
            # save() runs, to compute next_position() correctly.
            attrs["status"] = resolve_default_status(board.project)

        if is_create or "custom_fields" in attrs:
            item_type = attrs.get("item_type") or (
                self.instance.item_type if self.instance else WorkItem.ItemType.TASK
            )
            error = custom_fields_write_error(
                board.project, item_type, attrs.get("custom_fields", {}), existing_item=self.instance
            )
            if error:
                raise serializers.ValidationError({"custom_fields": error})

        return attrs

    def create(self, validated_data):
        custom_fields = validated_data.pop("custom_fields", None)
        instance = super().create(validated_data)
        if custom_fields:
            apply_custom_fields(instance, custom_fields)
        return instance

    def update(self, instance, validated_data):
        custom_fields = validated_data.pop("custom_fields", None)
        instance = super().update(instance, validated_data)
        if custom_fields is not None:
            apply_custom_fields(instance, custom_fields)
        return instance

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["custom_fields"] = custom_fields_read_map(instance)
        return data
```

Update `MoveWorkItemSerializer`:

```python
class MoveWorkItemSerializer(serializers.Serializer):
    status = serializers.PrimaryKeyRelatedField(queryset=WorkItemStatus.objects.all())
    position = serializers.IntegerField(min_value=0)
```

- [ ] **Step 10: Update `boards/views.py`**

`WorkItemViewSet.perform_create` — `status` is now always present in `validated_data` (Step 9's `validate()` guarantees it), so simplify:

```python
    def perform_create(self, serializer):
        board = serializer.validated_data["board"]
        status = serializer.validated_data["status"]
        serializer.save(
            created_by=self.request.user,
            position=next_position(board.id, status.id),
        )
```

`WorkItemViewSet.update`'s immutability check — fix the `status` comparison to use `item.status_id`, matching the pattern `board`/`board_id` already uses on the very next line:

```python
        if "status" in request.data or "board" in request.data or "item_type" in request.data or "key" in request.data:
            item = self.get_object()
            if "status" in request.data and str(request.data["status"]) != str(item.status_id):
                raise ValidationError(
                    {
                        "status": (
                            "Status cannot be changed here — "
                            "POST to /api/work-items/{id}/move/ instead."
                        )
                    }
                )
            if "board" in request.data and str(request.data["board"]) != str(item.board_id):
                raise ValidationError(
                    {
                        "board": "Work items cannot be moved between boards."
                    }
                )
            if "item_type" in request.data and request.data["item_type"] != item.item_type:
                raise ValidationError({"item_type": "Type cannot be changed after creation."})
            if "key" in request.data and request.data["key"] != item.key:
                raise ValidationError({"key": "Key cannot be changed."})
        return super().update(request, *args, **kwargs)
```

`WorkItemViewSet.move` — validate the target status belongs to this item's project before calling the service function, and pass an id through:

```python
    @action(detail=True, methods=["post"])
    def move(self, request, pk=None):
        item = self.get_object()

        serializer = MoveWorkItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target_status = serializer.validated_data["status"]
        if target_status.project_id != item.board.project_id:
            raise ValidationError({"status": "Status must belong to this item's project."})

        try:
            move_work_item(
                item,
                target_status.id,
                serializer.validated_data["position"],
            )
        except WorkItem.DoesNotExist:
            raise Http404("Work item was deleted before the move could be applied.")
        item.refresh_from_db()
        return Response(WorkItemSerializer(item).data)
```

Finally, add the real "still in use" guard to `WorkItemStatusViewSet.perform_destroy` (Task 1 shipped this method deliberately unguarded, since `WorkItem` didn't reference `WorkItemStatus` yet — now it does, via the `work_items_with_status` related name from Step 3):

```python
    def perform_destroy(self, instance):
        role = instance.project.memberships.get(user=self.request.user).role
        if not can_manage_statuses(role):
            raise PermissionDenied("You don't have permission to manage this project's statuses.")

        in_use = instance.work_items_with_status.count()
        if in_use:
            raise ValidationError(
                {"detail": f'"{instance.name}" is still used by {in_use} work item{"" if in_use == 1 else "s"}. Move {"it" if in_use == 1 else "them"} first.'}
            )
        remaining = WorkItemStatus.objects.filter(
            project=instance.project, category=instance.category
        ).exclude(pk=instance.pk)
        if not remaining.exists():
            raise ValidationError({"detail": f"{instance.get_category_display()} needs at least one status."})

        project = instance.project
        instance.delete()
        siblings = list(WorkItemStatus.objects.filter(project=project).order_by("position", "id"))
        for index, status in enumerate(siblings):
            if status.position != index:
                status.position = index
                status.save(update_fields=["position"])
```

(The last-in-category guard and the renumbering are unchanged from Task 1's version — only the new in-use check is added, ahead of them.)

- [ ] **Step 11: Update `boards/views_me.py`**

```python
from django.db.models import F
from rest_framework.generics import ListAPIView

from projects.models import ProjectMembership

from .models import WorkItem, WorkItemStatus
from .serializers import WorkItemSerializer


class MyTasksView(ListAPIView):
    """Everything assigned to me, in a project I still belong to, that is
    still open, soonest deadline first."""

    serializer_class = WorkItemSerializer
    pagination_class = None

    def get_queryset(self):
        member_project_ids = ProjectMembership.objects.filter(
            user=self.request.user
        ).values_list("project_id", flat=True)
        return (
            WorkItem.objects.filter(assignee=self.request.user, board__project_id__in=member_project_ids)
            .exclude(status__category=WorkItemStatus.Category.DONE)
            .select_related("board", "assignee", "created_by", "parent", "status")
            .prefetch_related("components", "field_values__field")
            .order_by(F("due_date").asc(nulls_last=True), "-priority", "id")
        )
```

- [ ] **Step 12: Repair `boards/management/commands/seed_demo.py`**

Update the import line to include the new service function:

```python
from boards.models import Board, WorkItem
from boards.services import seed_default_statuses
from projects.models import Project, ProjectMembership
```

After the `project, _ = Project.objects.get_or_create(...)` block, resolve the project's statuses once:

```python
        statuses = seed_default_statuses(project)
```

In the board/card loop, change `status=status` to look up the resolved object instead of passing the raw string, and keep the existing `counters` dict (still string-keyed — that bookkeeping is unrelated to the FK change):

```python
            counters = {"todo": 0, "in_progress": 0, "done": 0}
            for card_index, (title, status, priority, due_in_days) in enumerate(cards):
                WorkItem.objects.create(
                    board=board,
                    title=title,
                    description=f"Seeded card for {board_name}.",
                    status=statuses[status],
                    priority=priority,
                    due_date=None if due_in_days is None
                    else today + datetime.timedelta(days=due_in_days),
                    assignee=people[card_index % len(people)],
                    position=counters[status],
                    created_by=people[index % len(people)],
```

(Only the `status=` line inside the `WorkItem.objects.create(...)` call changes — `position=counters[status]` still indexes by the string, which is unaffected and correct as-is.)

- [ ] **Step 13: Repair `boards/tests/test_seed_demo.py`**

Change both `WorkItem.objects.filter(status=status)`-shaped queries (lines querying by category) to filter on the FK's category instead:

```python
@pytest.mark.django_db
def test_seed_fills_every_column():
    call_command("seed_demo")

    for category in ["todo", "in_progress", "done"]:
        assert WorkItem.objects.filter(status__category=category).exists()
```

```python
@pytest.mark.django_db
def test_seeded_positions_are_contiguous_within_each_column():
    call_command("seed_demo")

    for board in Board.objects.all():
        for category in ["todo", "in_progress", "done"]:
            positions = list(
                WorkItem.objects.filter(board=board, status__category=category)
                .order_by("position")
                .values_list("position", flat=True)
            )
            assert positions == list(range(len(positions)))
```

(Only these two test bodies change — rename their loop variable from `status` to `category` for clarity, matching what it now actually holds.)

- [ ] **Step 14: Repair `boards/tests/test_work_item_model.py`**

Replace the whole file:

```python
import datetime

import pytest

from boards.models import Board, WorkItem
from boards.services import next_position, seed_default_statuses


@pytest.fixture
def board(user, project):
    return Board.objects.create(name="Test Board", created_by=user, project=project)


@pytest.fixture
def statuses(project):
    return seed_default_statuses(project)


@pytest.mark.django_db
def test_work_item_defaults(board, statuses):
    item = WorkItem.objects.create(board=board, title="Write the spec")

    assert item.status_id == statuses["todo"].id
    assert item.priority == WorkItem.Priority.MEDIUM
    assert item.due_date is None
    assert item.assignee is None
    assert item.description == ""


@pytest.mark.django_db
def test_work_item_stringifies_to_its_title(board):
    assert str(WorkItem.objects.create(board=board, title="Ship it")) == "Ship it"


@pytest.mark.django_db
def test_next_position_starts_at_zero(board, statuses):
    assert next_position(board.id, statuses["todo"].id) == 0


@pytest.mark.django_db
def test_next_position_appends_to_the_end_of_its_column(board, statuses):
    WorkItem.objects.create(board=board, title="A", status=statuses["todo"], position=0)
    WorkItem.objects.create(board=board, title="B", status=statuses["todo"], position=1)

    assert next_position(board.id, statuses["todo"].id) == 2


@pytest.mark.django_db
def test_next_position_counts_each_column_separately(board, statuses):
    WorkItem.objects.create(board=board, title="A", status=statuses["todo"], position=0)
    WorkItem.objects.create(board=board, title="B", status=statuses["todo"], position=1)

    assert next_position(board.id, statuses["done"].id) == 0


@pytest.mark.django_db
def test_work_items_are_ordered_by_position_within_a_column(board, statuses):
    second = WorkItem.objects.create(board=board, title="Second", status=statuses["todo"], position=1)
    first = WorkItem.objects.create(board=board, title="First", status=statuses["todo"], position=0)

    assert list(WorkItem.objects.filter(status=statuses["todo"])) == [first, second]


@pytest.mark.django_db
def test_deleting_a_board_deletes_its_work_items(board):
    WorkItem.objects.create(board=board, title="Doomed")
    board.delete()
    assert WorkItem.objects.count() == 0


@pytest.mark.django_db
def test_unassigning_happens_when_the_assignee_is_deleted(board, other_user):
    item = WorkItem.objects.create(board=board, title="Orphan", assignee=other_user)
    other_user.delete()
    item.refresh_from_db()
    assert item.assignee is None


@pytest.mark.django_db
def test_due_date_can_be_set(board):
    item = WorkItem.objects.create(
        board=board, title="Dated", due_date=datetime.date(2026, 8, 15)
    )
    assert item.due_date == datetime.date(2026, 8, 15)
```

- [ ] **Step 15: Repair `boards/tests/test_work_item_api.py`**

Add `seed_default_statuses` to the imports and a `statuses` fixture (matching Step 14's), and make these targeted line changes:

```python
from boards.services import seed_default_statuses
```

```python
@pytest.fixture
def statuses(project):
    return seed_default_statuses(project)
```

- `test_creating_a_work_item_sets_creator_and_appends_it(auth_client, board, user, statuses)`: change `WorkItem.objects.create(board=board, title="Existing", status="todo", position=0)` to `WorkItem.objects.create(board=board, title="Existing", status=statuses["todo"], position=0)`, and change `assert body["status"] == "todo"` to `assert body["status_detail"]["category"] == "todo"`.
- `test_patching_status_is_rejected(auth_client, board, statuses)`: change the create call's `status="todo"` to `status=statuses["todo"]`, change the PATCH body to `{"status": statuses["done"].id}`, and change the final assertion from `assert item.status == "todo"` to `assert item.status_id == statuses["todo"].id`.
- `test_patching_with_status_unchanged_still_updates_other_fields(auth_client, board, statuses)`: change the create call's `status="todo"` to `status=statuses["todo"]`, the PATCH body's `"status": "todo"` to `"status": statuses["todo"].id`, and the final `assert item.status == "todo"` to `assert item.status_id == statuses["todo"].id`.
- `test_patching_title_still_works(auth_client, board, statuses)`: change the create call's `status="todo"` to `status=statuses["todo"]`, and the final `assert item.status == "todo"` to `assert item.status_id == statuses["todo"].id`.
- `test_patching_board_is_rejected(auth_client, board, user, project, statuses)`: change the create call's `status="todo"` to `status=statuses["todo"]` (the rest of this test is unaffected — it's about `board`, not `status`).
- `test_patching_with_board_unchanged_still_updates_other_fields(auth_client, board, statuses)`: change the create call's `status="todo"` to `status=statuses["todo"]`.
- `test_creating_a_work_item_with_an_explicit_status_still_works` — **delete this test entirely from this file**; it's superseded by the more precise version already written in Task 1's Step 1 file (`test_work_item_status_wiring.py`), which asserts against a real resolved id instead of a string literal.

- [ ] **Step 16: Repair `boards/tests/test_my_tasks.py`**

Add the same `seed_default_statuses` import and `statuses` fixture as Step 15. Change `test_finished_items_are_excluded`:

```python
@pytest.mark.django_db
def test_finished_items_are_excluded(auth_client, board, user, statuses):
    WorkItem.objects.create(board=board, title="Still going", assignee=user, status=statuses["todo"])
    WorkItem.objects.create(board=board, title="Finished", assignee=user, status=statuses["done"])

    response = auth_client.get("/api/me/tasks/")

    assert [item["title"] for item in response.json()] == ["Still going"]
```

(This test's category-spanning coverage — multiple *different* done-category statuses all excluded — is already covered by Step 1's `test_my_tasks_excludes_every_status_in_the_done_category` in the new file, so this one stays focused on the original single-status case it always tested.)

- [ ] **Step 17: Rewrite `boards/tests/test_work_item_move.py`**

Replace the whole file:

```python
import pytest

from boards.models import Board, WorkItem
from boards.services import move_work_item, seed_default_statuses
from boards.views import WorkItemViewSet


@pytest.fixture
def board(user, project):
    return Board.objects.create(name="Test Board", created_by=user, project=project)


@pytest.fixture
def statuses(project):
    return seed_default_statuses(project)


@pytest.fixture
def todo_items(board, statuses):
    return [
        WorkItem.objects.create(board=board, title=title, status=statuses["todo"], position=index)
        for index, title in enumerate(["A", "B", "C"])
    ]


def titles_in(board, status):
    return [
        item.title
        for item in WorkItem.objects.filter(board=board, status=status).order_by(
            "position", "id"
        )
    ]


@pytest.mark.django_db
def test_moving_a_work_item_up_within_its_column(auth_client, board, todo_items, statuses):
    item_c = todo_items[2]
    original_updated_at = item_c.updated_at

    response = auth_client.post(
        f"/api/work-items/{item_c.id}/move/",
        {"status": statuses["todo"].id, "position": 0},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert titles_in(board, statuses["todo"]) == ["C", "A", "B"]

    item_c.refresh_from_db()
    assert item_c.updated_at > original_updated_at


@pytest.mark.django_db
def test_moving_a_work_item_down_within_its_column(auth_client, board, todo_items, statuses):
    item_a = todo_items[0]

    auth_client.post(
        f"/api/work-items/{item_a.id}/move/",
        {"status": statuses["todo"].id, "position": 2},
        content_type="application/json",
    )

    assert titles_in(board, statuses["todo"]) == ["B", "C", "A"]


@pytest.mark.django_db
def test_moving_a_work_item_to_another_column(auth_client, board, todo_items, statuses):
    item_b = todo_items[1]

    response = auth_client.post(
        f"/api/work-items/{item_b.id}/move/",
        {"status": statuses["in_progress"].id, "position": 0},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["status"] == statuses["in_progress"].id
    assert titles_in(board, statuses["todo"]) == ["A", "C"]
    assert titles_in(board, statuses["in_progress"]) == ["B"]

    item_b.refresh_from_db()
    assert item_b.position == 0


@pytest.mark.django_db
def test_the_source_column_closes_its_gap(auth_client, board, todo_items, statuses):
    auth_client.post(
        f"/api/work-items/{todo_items[0].id}/move/",
        {"status": statuses["done"].id, "position": 0},
        content_type="application/json",
    )

    remaining = WorkItem.objects.filter(board=board, status=statuses["todo"]).order_by("position")
    assert [item.position for item in remaining] == [0, 1]


@pytest.mark.django_db
def test_dropping_into_the_middle_of_a_populated_column(auth_client, board, todo_items, statuses):
    WorkItem.objects.create(board=board, title="X", status=statuses["done"], position=0)
    WorkItem.objects.create(board=board, title="Y", status=statuses["done"], position=1)

    auth_client.post(
        f"/api/work-items/{todo_items[0].id}/move/",
        {"status": statuses["done"].id, "position": 1},
        content_type="application/json",
    )

    assert titles_in(board, statuses["done"]) == ["X", "A", "Y"]


@pytest.mark.django_db
def test_an_oversized_position_lands_at_the_end(auth_client, board, todo_items, statuses):
    auth_client.post(
        f"/api/work-items/{todo_items[0].id}/move/",
        {"status": statuses["todo"].id, "position": 999},
        content_type="application/json",
    )

    assert titles_in(board, statuses["todo"]) == ["B", "C", "A"]


@pytest.mark.django_db
def test_positions_stay_contiguous_from_zero(auth_client, board, todo_items, statuses):
    auth_client.post(
        f"/api/work-items/{todo_items[1].id}/move/",
        {"status": statuses["todo"].id, "position": 0},
        content_type="application/json",
    )

    positions = list(
        WorkItem.objects.filter(board=board, status=statuses["todo"])
        .order_by("position")
        .values_list("position", flat=True)
    )
    assert positions == [0, 1, 2]


@pytest.mark.django_db
def test_a_move_never_touches_another_board(auth_client, board, todo_items, user, project, statuses):
    other_board = Board.objects.create(name="Elsewhere", created_by=user, project=project)
    untouched = WorkItem.objects.create(
        board=other_board, title="Untouched", status=statuses["todo"], position=7
    )

    auth_client.post(
        f"/api/work-items/{todo_items[0].id}/move/",
        {"status": statuses["todo"].id, "position": 2},
        content_type="application/json",
    )

    untouched.refresh_from_db()
    assert untouched.position == 7


@pytest.mark.django_db
def test_an_unknown_status_is_rejected(auth_client, board, todo_items, statuses):
    response = auth_client.post(
        f"/api/work-items/{todo_items[0].id}/move/",
        {"status": 999999, "position": 0},
        content_type="application/json",
    )
    assert response.status_code == 400

    unchanged = list(
        WorkItem.objects.filter(board=board, status=statuses["todo"])
        .order_by("position")
        .values_list("title", "position")
    )
    assert unchanged == [("A", 0), ("B", 1), ("C", 2)]


@pytest.mark.django_db
def test_a_negative_position_is_rejected(auth_client, board, todo_items, statuses):
    response = auth_client.post(
        f"/api/work-items/{todo_items[0].id}/move/",
        {"status": statuses["todo"].id, "position": -1},
        content_type="application/json",
    )
    assert response.status_code == 400

    unchanged = list(
        WorkItem.objects.filter(board=board, status=statuses["todo"])
        .order_by("position")
        .values_list("title", "position")
    )
    assert unchanged == [("A", 0), ("B", 1), ("C", 2)]


@pytest.mark.django_db
def test_anonymous_callers_are_rejected(client, board, todo_items, statuses):
    response = client.post(
        f"/api/work-items/{todo_items[0].id}/move/",
        {"status": statuses["done"].id, "position": 0},
        content_type="application/json",
    )
    assert response.status_code == 403

    unchanged = list(
        WorkItem.objects.filter(board=board, status=statuses["todo"])
        .order_by("position")
        .values_list("title", "position")
    )
    assert unchanged == [("A", 0), ("B", 1), ("C", 2)]
    assert not WorkItem.objects.filter(board=board, status=statuses["done"]).exists()


@pytest.mark.django_db
def test_move_work_item_raises_when_the_row_was_deleted_after_it_was_fetched(
    board, todo_items, statuses
):
    """Direct service-level test of the Finding-1 race: the view's get_object()
    is unlocked, so by the time move_work_item() takes its row lock, another
    request may already have deleted the item. old_status_id must never be
    trusted from the stale in-memory instance, and the vanished row must not
    be reinserted as a ghost that shifts every real item in the destination
    column."""
    item = todo_items[0]
    WorkItem.objects.filter(pk=item.pk).delete()

    with pytest.raises(WorkItem.DoesNotExist):
        move_work_item(item, statuses["done"].id, 0)


@pytest.mark.django_db
def test_moving_a_work_item_deleted_after_it_was_fetched_returns_404(
    auth_client, board, todo_items, statuses, monkeypatch
):
    """Same race, exercised through the HTTP endpoint. get_object() is patched
    to return a stale WorkItem instance for a row that has since been
    deleted — standing in for a second request winning the race between this
    request's get_object() and its row lock. The endpoint must surface this
    as 404 (not 500), and it must not touch any other item on the board."""
    item = todo_items[0]
    WorkItem.objects.filter(pk=item.pk).delete()
    monkeypatch.setattr(WorkItemViewSet, "get_object", lambda self: item)

    response = auth_client.post(
        f"/api/work-items/{item.id}/move/",
        {"status": statuses["done"].id, "position": 0},
        content_type="application/json",
    )

    assert response.status_code == 404
    remaining = list(
        WorkItem.objects.filter(board=board, status=statuses["todo"])
        .order_by("position")
        .values_list("title", "position")
    )
    assert remaining == [("B", 1), ("C", 2)]
```

- [ ] **Step 18: Run the full suite**

Run: `docker compose run --rm web pytest boards/tests/test_work_item_status_wiring.py -v`
Expected: 9 passed.

Run: `docker compose run --rm web pytest -v`
Expected: all tests pass (292 total — 284 at the end of Task 1, +9 new from this task's own file (`test_work_item_status_wiring.py`), −1 from Step 15 deleting `test_creating_a_work_item_with_an_explicit_status_still_works` out of `test_work_item_api.py` with no direct replacement added to that file — the new file's own `test_creating_a_work_item_with_an_explicit_status_still_works` is that test's replacement, and is already counted in the +9. Steps 12, 13, 14, 16, and 17 rewrite existing test bodies in place without changing any file's test count.)

- [ ] **Step 19: Commit**

```bash
git add boards/ projects/views.py
git commit -m "Convert WorkItem.status to a per-project WorkItemStatus foreign key"
```

---

## Task 3: Documentation and final regression

**Files:**
- Modify: `docs/api.md`

**Interfaces:**
- Consumes: everything from Tasks 1-2.
- Produces: nothing new — brings `docs/api.md` up to date, which `CLAUDE.md` requires reading before writing any client code, and which this repo's own follow-ups file (`docs/follow-ups.md`) shows is easy to let drift (the `/api/cards/` rename already did, once).

- [ ] **Step 1: Update `docs/api.md`**

Read the current `docs/api.md` in full first. Add a new section (matching the style of the existing Components/Custom Fields sections) documenting:

- `GET/POST /api/projects/{id}/statuses/`, `PATCH/DELETE /api/projects/{id}/statuses/{id}/` — who can call each (any member for `GET`, Owner/Admin for writes), the last-in-category guard on both delete and recategorize, and the in-use delete guard.
- The **breaking change** to `POST /api/work-items/{id}/move/`: `status` in the request body is now a `WorkItemStatus` id, not one of the strings `"todo"`/`"in_progress"`/`"done"`. Flag this prominently — it is exactly the kind of thing `docs/follow-ups.md` already records once for the `/api/cards/` rename biting the UI unexpectedly ("Known breakage from the Work Item Hierarchy rename"). Add a line to `docs/follow-ups.md` itself, in that same style, noting that `design/js/store.js`/`ui/static/js/store.js` (whichever have landed by the time this is read) need to send a real status id here now, not a string.
- `WorkItemSerializer`'s new `status_detail` (`{id, name, category}`) and the `status` field's new meaning (an id, not an enum string) on `/api/work-items/` and `/api/boards/{id}/work-items/`.
- `MyTasksView`'s exclusion is now category-based ("every status tagged `done`", not "the literal status called Done") — worth a line in the "behaviors that bite" section, since a project that recategorizes a status changes what `/api/me/tasks/` shows without anyone touching that endpoint directly.

- [ ] **Step 2: Run the full suite one more time**

Run: `docker compose run --rm web pytest -v`
Expected: all tests pass (same total as the end of Task 2 — this step exists to catch anything Step 1's doc edit might have broken, which should be nothing, since it touches no code).

- [ ] **Step 3: Commit**

```bash
git add docs/api.md docs/follow-ups.md
git commit -m "Document Workflows endpoints and the move-endpoint status-id breaking change"
```

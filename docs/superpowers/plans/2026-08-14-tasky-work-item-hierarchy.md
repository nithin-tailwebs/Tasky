# Work Item Hierarchy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the production Django/DRF backend for Tasky's Work Item Hierarchy feature (sub-project 2a of 13) — rename `Card` to `WorkItem`, add issue types with a validated 3-level parent hierarchy, project-scoped unique keys, components, and symmetric "relates to" linking.

**Architecture:** `Card` becomes `WorkItem` in place (same `boards` app, same table via `RenameModel`), gaining `item_type`, `key`, and a self-referential `parent`. Hierarchy and same-board rules live in the serializer's object-level `validate()`, mirroring `design/js/logic.js`'s `isValidParent` exactly. Keys are generated under a row lock on `Project` (a real correctness requirement, unlike the deliberately-unlocked `next_position`). `Component` and `WorkItemLink` are new models in the same app.

**Tech Stack:** Django 5.2, DRF 3.16, MySQL, pytest-django. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-14-tasky-work-item-hierarchy-design.md` (signed off 2026-08-14; the `design/` prototype it argues from was signed off the same day)

## Global Constraints

- **Role vocabulary is `owner` / `admin` / `member`** (lowercase) — unchanged from sub-project 1, reused verbatim by `IsProjectMember` and `Logic.canManageComponents`'s backend equivalent in this plan.
- **A non-member touching anything gets `403`, not `404`; a genuinely missing id still `404`s.** This already works via `IsProjectMember` (object-level, unfiltered base queryset for detail actions, filtered `get_queryset()` for `list`) — every new endpoint in this plan follows the exact same pattern already established in `boards/views.py` and `projects/views.py`.
- **`item_type`, `key`, `status`, and `board` are all immutable after creation**, rejected with `400` via the existing raw-`request.data` inspection idiom in `WorkItemViewSet.update()` (the same pattern `status`/`board` already use) — never via the serializer, which never sees the rejected write.
- **Unauthenticated request → `403`, never `401`** (existing site-wide convention, unchanged).
- **Schema changes touching existing data need the nullable → backfill → required migration pattern**, not a direct `AddField(unique=True)` — `key`'s migration in Task 2 follows this exactly, mirroring `boards/migrations/0004`–`0006` from sub-project 1.

---

## Task 1: Rename `Card` → `WorkItem`, `/api/cards/` → `/api/work-items/`

**Files:**
- Modify: `boards/models.py`, `boards/serializers.py`, `boards/views.py`, `boards/urls.py`, `boards/services.py`, `boards/views_me.py`, `boards/admin.py`, `boards/management/commands/seed_demo.py`
- Create: `boards/migrations/0007_rename_card_to_workitem.py`
- Rename + modify: `boards/tests/test_card_api.py` → `boards/tests/test_work_item_api.py`, `boards/tests/test_card_model.py` → `boards/tests/test_work_item_model.py`, `boards/tests/test_card_move.py` → `boards/tests/test_work_item_move.py`
- Modify: `boards/tests/test_comments.py`, `boards/tests/test_my_tasks.py`, `boards/tests/test_project_scoping.py`, `boards/tests/test_seed_demo.py`

**Interfaces:**
- Consumes: nothing new — this task is a pure rename of code that already exists and already works.
- Produces: `boards.models.WorkItem` (identical fields to the old `Card`: `board`, `title`, `description`, `status`, `priority`, `due_date`, `assignee`, `position`, `created_by`, `created_at`, `updated_at`, plus the existing `project` property). `WorkItemSerializer`, `WorkItemViewSet`, `MoveWorkItemSerializer` — all later tasks build on these names. `board.work_items` is the new related-name accessor (was `board.cards`). `boards/services.py` now exports `move_work_item` (was `move_card`).

This task does not follow strict red-green TDD — it changes zero behavior, only names. The check for correctness is "the full suite (163 tests as of sub-project 1's merge) is still green under the new names," which is the final step.

- [ ] **Step 1: Rewrite `boards/models.py`**

```python
from django.conf import settings
from django.db import models


class Board(models.Model):
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="boards")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="boards_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name


class WorkItem(models.Model):
    class Status(models.TextChoices):
        TODO = "todo", "To Do"
        IN_PROGRESS = "in_progress", "In Progress"
        DONE = "done", "Done"

    class Priority(models.IntegerChoices):
        LOW = 1, "Low"
        MEDIUM = 2, "Medium"
        HIGH = 3, "High"

    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name="work_items")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.TODO
    )
    priority = models.IntegerField(
        choices=Priority.choices, default=Priority.MEDIUM
    )
    due_date = models.DateField(null=True, blank=True)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_work_items",
    )
    position = models.IntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="work_items_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]
        indexes = [models.Index(fields=["board", "status", "position"])]

    def __str__(self) -> str:
        return self.title

    @property
    def project(self):
        return self.board.project


class Comment(models.Model):
    card = models.ForeignKey(WorkItem, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="comments",
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return f"{self.author} on {self.card}"

    @property
    def project(self):
        return self.card.board.project
```

Note `Comment.card` keeps its field name — the spec only asks to rename the model, not every field that happens to reference it, and `Comment` isn't mentioned in the spec's scope at all.

- [ ] **Step 2: Hand-write the rename migration**

Do **not** run `makemigrations` interactively for this — hand-write it exactly as follows, so it's a guaranteed `RenameModel` (which preserves data and renames the underlying table automatically) rather than risking a non-interactive autodetection producing a data-losing drop-and-recreate:

Create `boards/migrations/0007_rename_card_to_workitem.py`:

```python
from django.conf import settings
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("boards", "0006_board_project_required"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameModel(old_name="Card", new_name="WorkItem"),
        migrations.AlterField(
            model_name="workitem",
            name="board",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="work_items",
                to="boards.board",
            ),
        ),
        migrations.AlterField(
            model_name="workitem",
            name="assignee",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="assigned_work_items",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="workitem",
            name="created_by",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="work_items_created",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
```

After writing this by hand, run `docker compose run --rm web python manage.py makemigrations --check --dry-run boards` — it should report no changes needed. If it reports a pending change, your hand-written migration doesn't exactly match the model state from Step 1; reconcile before continuing.

- [ ] **Step 3: Rewrite `boards/serializers.py`**

```python
from rest_framework import serializers

from accounts.serializers import UserSerializer

from .models import Board, Comment, WorkItem


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


class WorkItemSerializer(serializers.ModelSerializer):
    assignee_detail = UserSerializer(source="assignee", read_only=True)
    created_by = UserSerializer(read_only=True)
    priority_label = serializers.CharField(source="get_priority_display", read_only=True)

    class Meta:
        model = WorkItem
        fields = [
            "id", "board", "title", "description",
            "status", "priority", "priority_label", "due_date",
            "assignee", "assignee_detail",
            "position", "created_by", "created_at", "updated_at",
        ]
        read_only_fields = ["position"]

    def validate_board(self, value):
        request = self.context["request"]
        if not value.project.memberships.filter(user=request.user).exists():
            raise serializers.ValidationError("You must be a member of this board's project.")
        return value


class MoveWorkItemSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=WorkItem.Status.choices)
    position = serializers.IntegerField(min_value=0)


class CommentSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)

    class Meta:
        model = Comment
        fields = ["id", "card", "author", "body", "created_at"]
        read_only_fields = ["card"]

    def validate_body(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("A comment cannot be empty.")
        return value
```

- [ ] **Step 4: Rewrite `boards/views.py`**

```python
from django.http import Http404
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from projects.models import ProjectMembership
from projects.permissions import IsProjectMember

from .models import Board, Comment, WorkItem
from .serializers import (
    BoardSerializer,
    CommentSerializer,
    MoveWorkItemSerializer,
    WorkItemSerializer,
)
from .services import move_work_item, next_position


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
        # fine, a real change is rejected" rule WorkItem already applies to
        # status/board.
        if "project" in request.data:
            board = self.get_object()
            if str(request.data["project"]) != str(board.project_id):
                raise ValidationError({"project": "Boards cannot be moved between projects."})
        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=["get"], url_path="work-items")
    def work_items(self, request, pk=None):
        board = self.get_object()
        items = board.work_items.select_related("assignee", "created_by")
        return Response(WorkItemSerializer(items, many=True).data)


class WorkItemViewSet(viewsets.ModelViewSet):
    serializer_class = WorkItemSerializer
    pagination_class = None
    permission_classes = [IsAuthenticated, IsProjectMember]

    def get_queryset(self):
        qs = WorkItem.objects.select_related("board__project", "assignee", "created_by")
        if self.action == "list":
            qs = qs.filter(
                board__project_id__in=ProjectMembership.objects.filter(
                    user=self.request.user
                ).values_list("project_id", flat=True)
            )
        return qs

    def perform_create(self, serializer):
        board = serializer.validated_data["board"]
        status = serializer.validated_data.get("status", WorkItem.Status.TODO)
        serializer.save(
            created_by=self.request.user,
            position=next_position(board.id, status),
        )

    def update(self, request, *args, **kwargs):
        # Covers both PUT and PATCH: UpdateModelMixin.partial_update() just
        # calls this with partial=True. An actual status CHANGE here would
        # move the item between columns with NO renumbering — the source
        # keeps a gap, the destination gets a duplicate position — so that's
        # rejected in favour of the one route that renumbers correctly.
        # Only a real change is rejected: a UI that PATCHes back the full set
        # of fields it's holding (status included, unchanged, alongside a
        # genuine edit like title) must not have that legitimate edit 400'd
        # just because the status key was present in the body.
        # Same defect, same fix, for board: relocating an item to a different
        # board with a plain PATCH would leave a gap in the source column's
        # positions and a duplicate position in the destination column — no
        # renumbering happens either side. Work items do not move between
        # boards in this product at all, so unlike status there is no
        # endpoint to redirect to; a real change is just rejected outright.
        if "status" in request.data or "board" in request.data:
            item = self.get_object()
            if "status" in request.data and request.data["status"] != item.status:
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
        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def move(self, request, pk=None):
        item = self.get_object()

        serializer = MoveWorkItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            move_work_item(
                item,
                serializer.validated_data["status"],
                serializer.validated_data["position"],
            )
        except WorkItem.DoesNotExist:
            # The item was deleted by another request between this request's
            # (unlocked) get_object() and move_work_item()'s row lock.
            # WorkItem.DoesNotExist is not converted to 404 by DRF's default
            # exception handler on its own (only django.http.Http404 and
            # PermissionDenied are) — it has to be translated explicitly, or
            # this would surface as a 500.
            raise Http404("Work item was deleted before the move could be applied.")
        item.refresh_from_db()
        return Response(WorkItemSerializer(item).data)

    @action(detail=True, methods=["get", "post"])
    def comments(self, request, pk=None):
        item = self.get_object()

        if request.method == "POST":
            serializer = CommentSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save(card=item, author=request.user)
            return Response(serializer.data, status=201)

        thread = item.comments.select_related("author")
        return Response(CommentSerializer(thread, many=True).data)


class CommentViewSet(mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """Deletion only — comments are created through the work item's own endpoint."""

    serializer_class = CommentSerializer
    permission_classes = [IsAuthenticated, IsProjectMember]

    def get_queryset(self):
        return Comment.objects.select_related("author", "card__board__project")

    def perform_destroy(self, instance):
        # An authorless comment (its author's account was deleted, which
        # SET_NULLs this FK) must not become permanently undeletable.
        # `instance.author != self.request.user` is True for EVERY signed-in
        # user when author is None, which would brick deletion for good —
        # so ownership is only enforced when there is an owner to enforce.
        if instance.author_id is not None and instance.author != self.request.user:
            raise PermissionDenied("You can only delete your own comments.")
        instance.delete()
```

- [ ] **Step 5: Rewrite `boards/urls.py`**

```python
from rest_framework.routers import DefaultRouter

from .views import BoardViewSet, CommentViewSet, WorkItemViewSet

router = DefaultRouter()
router.register("boards", BoardViewSet, basename="board")
router.register("work-items", WorkItemViewSet, basename="work-item")
router.register("comments", CommentViewSet, basename="comment")

urlpatterns = router.urls
```

- [ ] **Step 6: Rewrite `boards/services.py`**

```python
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from .models import WorkItem


def next_position(board_id: int, status: str) -> int:
    """The position a new work item takes: the end of its column.

    This read is deliberately UNLOCKED. Two concurrent creates into the
    same column can both read the same Max(position) and both save with
    that same position — that duplicate is a real possible outcome, not a
    theoretical one. It is benign, and only benign, for two independent
    reasons that both have to keep holding:

    1. WorkItem.Meta.ordering = ["position", "id"] is a TOTAL order
       (position ties are broken by id), so a duplicate position never
       makes display order ambiguous or nondeterministic — it just makes
       the tie-break do the work "position" alone couldn't.
    2. move_work_item() renumbers the ENTIRE destination column to a clean
       0..n-1 on every move, not just the two rows it touches — so the
       very first drag in that column, by anyone, heals the duplicate.

    Anyone narrowing move_work_item() to shift only the immediate
    neighbours instead of renumbering the whole column, or dropping the
    `id` tiebreak from WorkItem.Meta.ordering, turns this from a harmless,
    self-healing quirk into a visible board-shuffle bug — two items
    fighting for the same slot with no defined order between them. Don't
    "fix" this by locking next_position(); the cost (a lock on every
    create) buys nothing that isn't already covered above.
    """
    highest = WorkItem.objects.filter(board_id=board_id, status=status).aggregate(
        highest=Max("position")
    )["highest"]
    return 0 if highest is None else highest + 1


@transaction.atomic
def move_work_item(item: WorkItem, new_status: str, new_position: int) -> WorkItem:
    """Drop a work item into a column at a position, then renumber the
    affected columns.

    The honest guarantee this module gives is NOT "positions are always a
    contiguous 0..n-1 for a column" — that is not a standing system
    invariant, and nothing enforces it outside of a move. Deleting the
    item at position 0 out of [0, 1, 2] leaves [1, 2] with no concurrency,
    no bug, and no renumbering involved — gaps like that are EXPECTED and
    HARMLESS, not a defect to fix (this module deliberately does not
    renumber on delete; see next_position() above for why a non-zero-based
    column is still safe to append to).

    What IS guaranteed: `position` (tie-broken by `id`, see
    WorkItem.Meta.ordering) gives every column a deterministic total
    order, and THIS function renormalises the columns it touches to a
    clean 0..n-1 at the moment it runs — that renumbering is a one-time
    side effect of a move, not an invariant that holds continuously
    afterward (the next delete reopens a gap, same as always). Every item
    on the board is locked with SELECT ... FOR UPDATE. That is heavier
    than locking two columns, but a board holds tens of rows, and it buys
    real safety: two concurrent moves on the SAME board issue the
    identical `WHERE board_id = ?` predicate against the same index, so
    both transactions scan (and therefore lock) the rows in the same
    order — that shared predicate/index is what makes them serialise
    instead of deadlocking. The trailing `order_by("id")` is a filesort
    applied to rows that are already locked by then; it gives the
    renumbering a stable, deterministic order to read in, but it plays no
    part in lock acquisition and is NOT what prevents the deadlock. Moves
    on different boards lock disjoint row sets and never contend at all.
    Do not narrow this to a two-column lock on the theory that the ORDER
    BY protects it — it doesn't; any narrower filter would need its own
    argument for why it stays deadlock-free.
    """
    locked = list(
        WorkItem.objects.select_for_update()
        .filter(board_id=item.board_id)
        .order_by("id")
    )

    locked_by_pk = {c.pk: c for c in locked}
    if item.pk not in locked_by_pk:
        # `item` was fetched (unlocked) by the view before this transaction
        # took the lock. If another request deleted it in between, trusting
        # `item.status` here would use a stale, possibly-wrong old_status,
        # renumbering the wrong column, and inserting `item` into the
        # destination column would resurrect a ghost row that bulk_update
        # never writes, leaving the destination with a hole. Surface it as
        # "gone" instead.
        raise WorkItem.DoesNotExist(
            f"WorkItem {item.pk} was deleted before the move could be applied."
        )

    old_status = locked_by_pk[item.pk].status
    item.status = new_status

    def renumber(status: str) -> list[WorkItem]:
        column = [c for c in locked if c.status == status and c.pk != item.pk]
        column.sort(key=lambda c: (c.position, c.pk))

        if status == new_status:
            index = max(0, min(new_position, len(column)))
            column.insert(index, item)

        now = timezone.now()
        for index, member in enumerate(column):
            member.position = index
            member.updated_at = now
        return column

    touched = renumber(new_status)
    if old_status != new_status:
        touched += renumber(old_status)

    WorkItem.objects.bulk_update(touched, ["position", "status", "updated_at"])
    return item
```

- [ ] **Step 7: Rewrite `boards/views_me.py`**

```python
from django.db.models import F
from rest_framework.generics import ListAPIView

from projects.models import ProjectMembership

from .models import WorkItem
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
            .exclude(status=WorkItem.Status.DONE)
            .select_related("board", "assignee", "created_by")
            .order_by(F("due_date").asc(nulls_last=True), "-priority", "id")
        )
```

- [ ] **Step 8: Rewrite `boards/admin.py`**

```python
from django.contrib import admin

from .models import Board, Comment, WorkItem


@admin.register(Board)
class BoardAdmin(admin.ModelAdmin):
    list_display = ["name", "created_by", "created_at"]
    search_fields = ["name"]


@admin.register(WorkItem)
class WorkItemAdmin(admin.ModelAdmin):
    list_display = ["title", "board", "status", "priority", "assignee", "due_date"]
    list_filter = ["status", "priority", "board"]
    search_fields = ["title", "description"]
    readonly_fields = ["position"]


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ["card", "author", "created_at"]
    search_fields = ["body"]
```

- [ ] **Step 9: Update `boards/management/commands/seed_demo.py`**

Change the import line:

```python
from boards.models import Board, WorkItem
```

Change the `Card.objects.create(...)` call inside the `for card_index, (title, status, priority, due_in_days) in enumerate(cards):` loop to `WorkItem.objects.create(...)` (same arguments, unchanged) — and update the final summary message:

```python
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {Board.objects.count()} boards, "
                f"{WorkItem.objects.count()} work items. "
                f"Demo logins use the password: {DEMO_PASSWORD}"
            )
        )
```

- [ ] **Step 10: Rename and rewrite the three Card-named test files**

Delete `boards/tests/test_card_api.py`, create `boards/tests/test_work_item_api.py`:

```python
import pytest

from boards.models import Board, WorkItem


@pytest.fixture
def board(user, project):
    return Board.objects.create(name="Test Board", created_by=user, project=project)


@pytest.mark.django_db
def test_anonymous_callers_are_rejected(client, board):
    assert client.get(f"/api/boards/{board.id}/work-items/").status_code == 403


@pytest.mark.django_db
def test_listing_a_boards_work_items(auth_client, board, user, project):
    WorkItem.objects.create(board=board, title="First", position=0)
    WorkItem.objects.create(board=board, title="Second", position=1)
    other_board = Board.objects.create(name="Elsewhere", created_by=user, project=project)
    WorkItem.objects.create(board=other_board, title="Not mine")

    response = auth_client.get(f"/api/boards/{board.id}/work-items/")

    assert response.status_code == 200
    assert [item["title"] for item in response.json()] == ["First", "Second"]


@pytest.mark.django_db
def test_creating_a_work_item_sets_creator_and_appends_it(auth_client, board, user):
    WorkItem.objects.create(board=board, title="Existing", status="todo", position=0)

    response = auth_client.post(
        "/api/work-items/",
        {"board": board.id, "title": "New item"},
        content_type="application/json",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["position"] == 1
    assert body["status"] == "todo"
    assert body["priority"] == 2
    assert body["priority_label"] == "Medium"
    assert WorkItem.objects.get(title="New item").created_by == user


@pytest.mark.django_db
def test_creating_a_work_item_with_an_assignee_and_a_due_date(auth_client, board, other_user):
    response = auth_client.post(
        "/api/work-items/",
        {
            "board": board.id,
            "title": "Assigned",
            "assignee": other_user.id,
            "due_date": "2026-08-15",
            "priority": 3,
        },
        content_type="application/json",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["assignee_detail"]["username"] == "bob"
    assert body["due_date"] == "2026-08-15"
    assert body["priority_label"] == "High"


@pytest.mark.django_db
def test_editing_a_work_item(auth_client, board):
    item = WorkItem.objects.create(board=board, title="Before")

    response = auth_client.patch(
        f"/api/work-items/{item.id}/",
        {"title": "After", "description": "Now with detail"},
        content_type="application/json",
    )

    assert response.status_code == 200
    item.refresh_from_db()
    assert item.title == "After"
    assert item.description == "Now with detail"


@pytest.mark.django_db
def test_unassigning_a_work_item(auth_client, board, other_user):
    item = WorkItem.objects.create(board=board, title="Assigned", assignee=other_user)

    response = auth_client.patch(
        f"/api/work-items/{item.id}/",
        {"assignee": None},
        content_type="application/json",
    )

    assert response.status_code == 200
    item.refresh_from_db()
    assert item.assignee is None


@pytest.mark.django_db
def test_listing_all_work_items_is_unscoped_by_board(auth_client, board, user, project):
    other_board = Board.objects.create(name="Elsewhere", created_by=user, project=project)
    WorkItem.objects.create(board=board, title="Mine", position=0)
    WorkItem.objects.create(board=other_board, title="Also visible", position=0)

    response = auth_client.get("/api/work-items/")

    assert response.status_code == 200
    assert {item["title"] for item in response.json()} == {"Mine", "Also visible"}


@pytest.mark.django_db
def test_retrieving_a_single_work_item(auth_client, board):
    item = WorkItem.objects.create(board=board, title="One item", position=0)

    response = auth_client.get(f"/api/work-items/{item.id}/")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == item.id
    assert body["title"] == "One item"


@pytest.mark.django_db
def test_deleting_a_work_item(auth_client, board):
    item = WorkItem.objects.create(board=board, title="Doomed")
    assert auth_client.delete(f"/api/work-items/{item.id}/").status_code == 204
    assert not WorkItem.objects.filter(id=item.id).exists()


@pytest.mark.django_db
def test_position_cannot_be_set_directly(auth_client, board):
    response = auth_client.post(
        "/api/work-items/",
        {"board": board.id, "title": "Sneaky", "position": 99},
        content_type="application/json",
    )

    assert response.status_code == 201
    assert response.json()["position"] == 0


@pytest.mark.django_db
def test_title_is_required(auth_client, board):
    response = auth_client.post(
        "/api/work-items/", {"board": board.id}, content_type="application/json"
    )
    assert response.status_code == 400
    assert "title" in response.json()


@pytest.mark.django_db
def test_patching_status_is_rejected(auth_client, board):
    item = WorkItem.objects.create(board=board, title="Untouched", status="todo")

    response = auth_client.patch(
        f"/api/work-items/{item.id}/",
        {"status": "done"},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "status" in response.json()
    item.refresh_from_db()
    assert item.status == "todo"


@pytest.mark.django_db
def test_patching_with_status_unchanged_still_updates_other_fields(auth_client, board):
    """A UI that PATCHes back the full set of fields it's holding — status
    included, but unchanged — must not have a genuine edit (title, here)
    rejected just because "status" was present in the body. Only an actual
    status CHANGE is rejected."""
    item = WorkItem.objects.create(board=board, title="Before", status="todo")

    response = auth_client.patch(
        f"/api/work-items/{item.id}/",
        {"status": "todo", "title": "After"},
        content_type="application/json",
    )

    assert response.status_code == 200
    item.refresh_from_db()
    assert item.title == "After"
    assert item.status == "todo"


@pytest.mark.django_db
def test_patching_title_still_works(auth_client, board):
    item = WorkItem.objects.create(board=board, title="Before", status="todo")

    response = auth_client.patch(
        f"/api/work-items/{item.id}/",
        {"title": "After"},
        content_type="application/json",
    )

    assert response.status_code == 200
    item.refresh_from_db()
    assert item.title == "After"
    assert item.status == "todo"


@pytest.mark.django_db
def test_patching_board_is_rejected(auth_client, board, user, project):
    other_board = Board.objects.create(name="Elsewhere", created_by=user, project=project)
    item = WorkItem.objects.create(board=board, title="Untouched", status="todo")

    response = auth_client.patch(
        f"/api/work-items/{item.id}/",
        {"board": other_board.id},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "board" in response.json()
    item.refresh_from_db()
    assert item.board_id == board.id


@pytest.mark.django_db
def test_patching_with_board_unchanged_still_updates_other_fields(auth_client, board):
    """Same protection as status: a PATCH that echoes back the item's
    current, unchanged board alongside a genuine edit (title, here) must
    not be rejected just because "board" was present in the body."""
    item = WorkItem.objects.create(board=board, title="Before", status="todo")

    response = auth_client.patch(
        f"/api/work-items/{item.id}/",
        {"board": board.id, "title": "After"},
        content_type="application/json",
    )

    assert response.status_code == 200
    item.refresh_from_db()
    assert item.title == "After"
    assert item.board_id == board.id


@pytest.mark.django_db
def test_creating_a_work_item_with_an_explicit_status_still_works(auth_client, board):
    response = auth_client.post(
        "/api/work-items/",
        {"board": board.id, "title": "Started already", "status": "in_progress"},
        content_type="application/json",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "in_progress"
    assert body["position"] == 0
    assert WorkItem.objects.get(title="Started already").status == "in_progress"
```

Delete `boards/tests/test_card_model.py`, create `boards/tests/test_work_item_model.py`:

```python
import datetime

import pytest

from boards.models import Board, WorkItem
from boards.services import next_position


@pytest.fixture
def board(user, project):
    return Board.objects.create(name="Test Board", created_by=user, project=project)


@pytest.mark.django_db
def test_work_item_defaults(board):
    item = WorkItem.objects.create(board=board, title="Write the spec")

    assert item.status == WorkItem.Status.TODO
    assert item.priority == WorkItem.Priority.MEDIUM
    assert item.due_date is None
    assert item.assignee is None
    assert item.description == ""


@pytest.mark.django_db
def test_work_item_stringifies_to_its_title(board):
    assert str(WorkItem.objects.create(board=board, title="Ship it")) == "Ship it"


@pytest.mark.django_db
def test_next_position_starts_at_zero(board):
    assert next_position(board.id, WorkItem.Status.TODO) == 0


@pytest.mark.django_db
def test_next_position_appends_to_the_end_of_its_column(board):
    WorkItem.objects.create(board=board, title="A", status=WorkItem.Status.TODO, position=0)
    WorkItem.objects.create(board=board, title="B", status=WorkItem.Status.TODO, position=1)

    assert next_position(board.id, WorkItem.Status.TODO) == 2


@pytest.mark.django_db
def test_next_position_counts_each_column_separately(board):
    WorkItem.objects.create(board=board, title="A", status=WorkItem.Status.TODO, position=0)
    WorkItem.objects.create(board=board, title="B", status=WorkItem.Status.TODO, position=1)

    assert next_position(board.id, WorkItem.Status.DONE) == 0


@pytest.mark.django_db
def test_work_items_are_ordered_by_position_within_a_column(board):
    second = WorkItem.objects.create(board=board, title="Second", position=1)
    first = WorkItem.objects.create(board=board, title="First", position=0)

    assert list(WorkItem.objects.filter(status=WorkItem.Status.TODO)) == [first, second]


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

Delete `boards/tests/test_card_move.py`, create `boards/tests/test_work_item_move.py`:

```python
import pytest

from boards.models import Board, WorkItem
from boards.services import move_work_item
from boards.views import WorkItemViewSet


@pytest.fixture
def board(user, project):
    return Board.objects.create(name="Test Board", created_by=user, project=project)


@pytest.fixture
def todo_items(board):
    return [
        WorkItem.objects.create(board=board, title=title, status="todo", position=index)
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
def test_moving_a_work_item_up_within_its_column(auth_client, board, todo_items):
    item_c = todo_items[2]
    original_updated_at = item_c.updated_at

    response = auth_client.post(
        f"/api/work-items/{item_c.id}/move/",
        {"status": "todo", "position": 0},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert titles_in(board, "todo") == ["C", "A", "B"]

    item_c.refresh_from_db()
    assert item_c.updated_at > original_updated_at


@pytest.mark.django_db
def test_moving_a_work_item_down_within_its_column(auth_client, board, todo_items):
    item_a = todo_items[0]

    auth_client.post(
        f"/api/work-items/{item_a.id}/move/",
        {"status": "todo", "position": 2},
        content_type="application/json",
    )

    assert titles_in(board, "todo") == ["B", "C", "A"]


@pytest.mark.django_db
def test_moving_a_work_item_to_another_column(auth_client, board, todo_items):
    item_b = todo_items[1]

    response = auth_client.post(
        f"/api/work-items/{item_b.id}/move/",
        {"status": "in_progress", "position": 0},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"
    assert titles_in(board, "todo") == ["A", "C"]
    assert titles_in(board, "in_progress") == ["B"]

    item_b.refresh_from_db()
    assert item_b.position == 0


@pytest.mark.django_db
def test_the_source_column_closes_its_gap(auth_client, board, todo_items):
    auth_client.post(
        f"/api/work-items/{todo_items[0].id}/move/",
        {"status": "done", "position": 0},
        content_type="application/json",
    )

    remaining = WorkItem.objects.filter(board=board, status="todo").order_by("position")
    assert [item.position for item in remaining] == [0, 1]


@pytest.mark.django_db
def test_dropping_into_the_middle_of_a_populated_column(auth_client, board, todo_items):
    WorkItem.objects.create(board=board, title="X", status="done", position=0)
    WorkItem.objects.create(board=board, title="Y", status="done", position=1)

    auth_client.post(
        f"/api/work-items/{todo_items[0].id}/move/",
        {"status": "done", "position": 1},
        content_type="application/json",
    )

    assert titles_in(board, "done") == ["X", "A", "Y"]


@pytest.mark.django_db
def test_an_oversized_position_lands_at_the_end(auth_client, board, todo_items):
    auth_client.post(
        f"/api/work-items/{todo_items[0].id}/move/",
        {"status": "todo", "position": 999},
        content_type="application/json",
    )

    assert titles_in(board, "todo") == ["B", "C", "A"]


@pytest.mark.django_db
def test_positions_stay_contiguous_from_zero(auth_client, board, todo_items):
    auth_client.post(
        f"/api/work-items/{todo_items[1].id}/move/",
        {"status": "todo", "position": 0},
        content_type="application/json",
    )

    positions = list(
        WorkItem.objects.filter(board=board, status="todo")
        .order_by("position")
        .values_list("position", flat=True)
    )
    assert positions == [0, 1, 2]


@pytest.mark.django_db
def test_a_move_never_touches_another_board(auth_client, board, todo_items, user, project):
    other_board = Board.objects.create(name="Elsewhere", created_by=user, project=project)
    untouched = WorkItem.objects.create(
        board=other_board, title="Untouched", status="todo", position=7
    )

    auth_client.post(
        f"/api/work-items/{todo_items[0].id}/move/",
        {"status": "todo", "position": 2},
        content_type="application/json",
    )

    untouched.refresh_from_db()
    assert untouched.position == 7


@pytest.mark.django_db
def test_an_unknown_status_is_rejected(auth_client, board, todo_items):
    response = auth_client.post(
        f"/api/work-items/{todo_items[0].id}/move/",
        {"status": "archived", "position": 0},
        content_type="application/json",
    )
    assert response.status_code == 400

    # A 400 must mean nothing was written, not just that the response looks
    # right — check the rows directly rather than trusting the status code alone.
    unchanged = list(
        WorkItem.objects.filter(board=board, status="todo")
        .order_by("position")
        .values_list("title", "position")
    )
    assert unchanged == [("A", 0), ("B", 1), ("C", 2)]


@pytest.mark.django_db
def test_a_negative_position_is_rejected(auth_client, board, todo_items):
    response = auth_client.post(
        f"/api/work-items/{todo_items[0].id}/move/",
        {"status": "todo", "position": -1},
        content_type="application/json",
    )
    assert response.status_code == 400

    unchanged = list(
        WorkItem.objects.filter(board=board, status="todo")
        .order_by("position")
        .values_list("title", "position")
    )
    assert unchanged == [("A", 0), ("B", 1), ("C", 2)]


@pytest.mark.django_db
def test_anonymous_callers_are_rejected(client, board, todo_items):
    response = client.post(
        f"/api/work-items/{todo_items[0].id}/move/",
        {"status": "done", "position": 0},
        content_type="application/json",
    )
    assert response.status_code == 403

    unchanged = list(
        WorkItem.objects.filter(board=board, status="todo")
        .order_by("position")
        .values_list("title", "position")
    )
    assert unchanged == [("A", 0), ("B", 1), ("C", 2)]
    assert not WorkItem.objects.filter(board=board, status="done").exists()


@pytest.mark.django_db
def test_move_work_item_raises_when_the_row_was_deleted_after_it_was_fetched(
    board, todo_items
):
    """Direct service-level test of the Finding-1 race: the view's get_object()
    is unlocked, so by the time move_work_item() takes its row lock, another
    request may already have deleted the item. old_status must never be
    trusted from the stale in-memory instance, and the vanished row must not
    be reinserted as a ghost that shifts every real item in the destination
    column."""
    item = todo_items[0]
    WorkItem.objects.filter(pk=item.pk).delete()

    with pytest.raises(WorkItem.DoesNotExist):
        move_work_item(item, "done", 0)


@pytest.mark.django_db
def test_moving_a_work_item_deleted_after_it_was_fetched_returns_404(
    auth_client, board, todo_items, monkeypatch
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
        {"status": "done", "position": 0},
        content_type="application/json",
    )

    assert response.status_code == 404
    remaining = list(
        WorkItem.objects.filter(board=board, status="todo")
        .order_by("position")
        .values_list("title", "position")
    )
    assert remaining == [("B", 1), ("C", 2)]
```

- [ ] **Step 11: Update `boards/tests/test_comments.py`**

```python
import pytest

from boards.models import Board, Comment, WorkItem


@pytest.fixture
def board(user, project):
    return Board.objects.create(name="Test Board", created_by=user, project=project)


@pytest.fixture
def work_item(board):
    return WorkItem.objects.create(board=board, title="Discuss me")


@pytest.mark.django_db
def test_anonymous_callers_are_rejected(client, work_item):
    assert client.get(f"/api/work-items/{work_item.id}/comments/").status_code == 403


@pytest.mark.django_db
def test_posting_a_comment_records_the_author(auth_client, work_item, user):
    response = auth_client.post(
        f"/api/work-items/{work_item.id}/comments/",
        {"body": "Started on this"},
        content_type="application/json",
    )

    assert response.status_code == 201
    assert response.json()["author"]["username"] == "alice"
    assert Comment.objects.get(card=work_item).author == user


@pytest.mark.django_db
def test_comments_come_back_oldest_first(auth_client, work_item, user):
    Comment.objects.create(card=work_item, author=user, body="First")
    Comment.objects.create(card=work_item, author=user, body="Second")

    response = auth_client.get(f"/api/work-items/{work_item.id}/comments/")

    assert [comment["body"] for comment in response.json()] == ["First", "Second"]


@pytest.mark.django_db
def test_comments_are_scoped_to_their_work_item(auth_client, board, work_item, user):
    other_item = WorkItem.objects.create(board=board, title="Elsewhere")
    Comment.objects.create(card=work_item, author=user, body="Mine")
    Comment.objects.create(card=other_item, author=user, body="Not mine")

    response = auth_client.get(f"/api/work-items/{work_item.id}/comments/")

    assert [comment["body"] for comment in response.json()] == ["Mine"]


@pytest.mark.django_db
def test_an_author_can_delete_their_own_comment(auth_client, work_item, user):
    comment = Comment.objects.create(card=work_item, author=user, body="Mine to delete")

    assert auth_client.delete(f"/api/comments/{comment.id}/").status_code == 204
    assert not Comment.objects.filter(id=comment.id).exists()


@pytest.mark.django_db
def test_nobody_can_delete_someone_elses_comment(auth_client, work_item, other_user):
    comment = Comment.objects.create(card=work_item, author=other_user, body="Not yours")

    assert auth_client.delete(f"/api/comments/{comment.id}/").status_code == 403
    assert Comment.objects.filter(id=comment.id).exists()


@pytest.mark.django_db
def test_an_authorless_comment_can_be_deleted_by_anyone_signed_in(auth_client, work_item, other_user):
    """author is SET_NULL when the author's account is deleted. Ownership
    must only be enforced when there IS an owner, or the comment becomes
    permanently undeletable — everyone fails `author != request.user` when
    author is None."""
    comment = Comment.objects.create(card=work_item, author=other_user, body="Orphaned")
    other_user.delete()
    comment.refresh_from_db()
    assert comment.author_id is None

    assert auth_client.delete(f"/api/comments/{comment.id}/").status_code == 204
    assert not Comment.objects.filter(id=comment.id).exists()


@pytest.mark.django_db
def test_an_empty_comment_is_rejected(auth_client, work_item):
    response = auth_client.post(
        f"/api/work-items/{work_item.id}/comments/",
        {"body": "   "},
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_deleting_a_work_item_deletes_its_comments(auth_client, work_item, user):
    Comment.objects.create(card=work_item, author=user, body="Goes with the item")
    work_item.delete()
    assert Comment.objects.count() == 0
```

- [ ] **Step 12: Update `boards/tests/test_my_tasks.py`**

```python
import datetime

import pytest

from boards.models import Board, WorkItem


@pytest.fixture
def board(user, project):
    return Board.objects.create(name="Test Board", created_by=user, project=project)


@pytest.mark.django_db
def test_anonymous_callers_are_rejected(client):
    assert client.get("/api/me/tasks/").status_code == 403


@pytest.mark.django_db
def test_only_my_work_items_come_back(auth_client, board, user, other_user):
    WorkItem.objects.create(board=board, title="Mine", assignee=user)
    WorkItem.objects.create(board=board, title="Theirs", assignee=other_user)
    WorkItem.objects.create(board=board, title="Nobody's")

    response = auth_client.get("/api/me/tasks/")

    assert response.status_code == 200
    assert [item["title"] for item in response.json()] == ["Mine"]


@pytest.mark.django_db
def test_my_work_items_span_every_board(auth_client, board, user, project):
    second_board = Board.objects.create(name="Second", created_by=user, project=project)
    WorkItem.objects.create(board=board, title="From board one", assignee=user)
    WorkItem.objects.create(board=second_board, title="From board two", assignee=user)

    response = auth_client.get("/api/me/tasks/")

    assert {item["title"] for item in response.json()} == {
        "From board one",
        "From board two",
    }


@pytest.mark.django_db
def test_soonest_due_first_with_undated_items_last(auth_client, board, user):
    WorkItem.objects.create(board=board, title="No date", assignee=user)
    WorkItem.objects.create(
        board=board, title="Later", assignee=user, due_date=datetime.date(2026, 9, 1)
    )
    WorkItem.objects.create(
        board=board, title="Sooner", assignee=user, due_date=datetime.date(2026, 8, 1)
    )

    response = auth_client.get("/api/me/tasks/")

    assert [item["title"] for item in response.json()] == ["Sooner", "Later", "No date"]


@pytest.mark.django_db
def test_undated_items_break_ties_on_priority(auth_client, board, user):
    WorkItem.objects.create(board=board, title="Low", assignee=user, priority=1)
    WorkItem.objects.create(board=board, title="High", assignee=user, priority=3)

    response = auth_client.get("/api/me/tasks/")

    assert [item["title"] for item in response.json()] == ["High", "Low"]


@pytest.mark.django_db
def test_finished_items_are_excluded(auth_client, board, user):
    WorkItem.objects.create(board=board, title="Still going", assignee=user, status="todo")
    WorkItem.objects.create(board=board, title="Finished", assignee=user, status="done")

    response = auth_client.get("/api/me/tasks/")

    assert [item["title"] for item in response.json()] == ["Still going"]
```

- [ ] **Step 13: Update `boards/tests/test_project_scoping.py`**

```python
import pytest

from boards.models import Board, Comment, WorkItem
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
def test_a_non_member_cannot_list_a_boards_work_items(auth_client, other_user, foreign_project):
    board = Board.objects.create(name="Hidden", created_by=other_user, project=foreign_project)
    WorkItem.objects.create(board=board, title="Secret")

    assert auth_client.get(f"/api/boards/{board.id}/work-items/").status_code == 403


@pytest.mark.django_db
def test_work_items_list_is_scoped_to_my_projects(auth_client, user, project, other_user, foreign_project):
    mine = Board.objects.create(name="Mine", created_by=user, project=project)
    WorkItem.objects.create(board=mine, title="Visible")
    theirs = Board.objects.create(name="Theirs", created_by=other_user, project=foreign_project)
    WorkItem.objects.create(board=theirs, title="Hidden")

    response = auth_client.get("/api/work-items/")

    assert response.status_code == 200
    titles = {i["title"] for i in response.json()}
    assert titles == {"Visible"}


@pytest.mark.django_db
def test_a_non_member_cannot_retrieve_a_work_item(auth_client, other_user, foreign_project):
    board = Board.objects.create(name="Hidden", created_by=other_user, project=foreign_project)
    item = WorkItem.objects.create(board=board, title="Secret")

    assert auth_client.get(f"/api/work-items/{item.id}/").status_code == 403


@pytest.mark.django_db
def test_cannot_create_a_work_item_on_a_board_in_a_project_you_do_not_belong_to(auth_client, other_user, foreign_project):
    board = Board.objects.create(name="Hidden", created_by=other_user, project=foreign_project)

    response = auth_client.post(
        "/api/work-items/", {"board": board.id, "title": "Sneaky"}, content_type="application/json"
    )

    assert response.status_code == 400
    assert "board" in response.json()


@pytest.mark.django_db
def test_a_non_member_cannot_delete_someones_elses_comment(auth_client, other_user, foreign_project):
    board = Board.objects.create(name="Hidden", created_by=other_user, project=foreign_project)
    item = WorkItem.objects.create(board=board, title="Secret")
    comment = Comment.objects.create(card=item, author=other_user, body="Not yours to see")

    assert auth_client.delete(f"/api/comments/{comment.id}/").status_code == 403


@pytest.mark.django_db
def test_a_non_member_cannot_delete_an_authorless_comment_in_a_foreign_project(auth_client, other_user, foreign_project):
    board = Board.objects.create(name="Hidden", created_by=other_user, project=foreign_project)
    item = WorkItem.objects.create(board=board, title="Secret")
    comment = Comment.objects.create(card=item, author=None, body="Orphaned, in a project you're not in")

    assert auth_client.delete(f"/api/comments/{comment.id}/").status_code == 403


@pytest.mark.django_db
def test_my_tasks_only_shows_tasks_in_my_projects(auth_client, user, project, other_user, foreign_project):
    mine = Board.objects.create(name="Mine", created_by=user, project=project)
    WorkItem.objects.create(board=mine, title="Mine to do", assignee=user)

    theirs = Board.objects.create(name="Theirs", created_by=other_user, project=foreign_project)
    # Same user assigned in a project they've since left/never joined:
    WorkItem.objects.create(board=theirs, title="Not mine to see", assignee=user)

    response = auth_client.get("/api/me/tasks/")

    assert response.status_code == 200
    titles = {i["title"] for i in response.json()}
    assert titles == {"Mine to do"}
```

- [ ] **Step 14: Update `boards/tests/test_seed_demo.py`**

Change the import line:

```python
from boards.models import Board, WorkItem
```

Replace every `Card` reference with `WorkItem`, and rename the first test function:

```python
import io

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection

from boards.models import Board, WorkItem


@pytest.mark.django_db
def test_seed_creates_boards_users_and_work_items():
    call_command("seed_demo")

    assert Board.objects.count() == 2
    assert WorkItem.objects.count() >= 8
    assert get_user_model().objects.filter(is_active=True).count() >= 3


@pytest.mark.django_db
def test_seed_fills_every_column():
    call_command("seed_demo")

    for status in ["todo", "in_progress", "done"]:
        assert WorkItem.objects.filter(status=status).exists()


@pytest.mark.django_db
def test_seed_is_safe_to_run_twice():
    call_command("seed_demo")
    call_command("seed_demo")

    assert Board.objects.count() == 2


@pytest.mark.django_db
def test_seeded_positions_are_contiguous_within_each_column():
    call_command("seed_demo")

    for board in Board.objects.all():
        for status in ["todo", "in_progress", "done"]:
            positions = list(
                WorkItem.objects.filter(board=board, status=status)
                .order_by("position")
                .values_list("position", flat=True)
            )
            assert positions == list(range(len(positions)))


@pytest.mark.django_db
def test_seed_warns_which_database_it_is_about_to_write_to():
    out = io.StringIO()
    call_command("seed_demo", stdout=out)

    output = out.getvalue()
    assert connection.settings_dict["NAME"] in output
    assert "NEVER" in output
    assert "production" in output.lower()
```

- [ ] **Step 15: Run migrations and the full suite**

```bash
docker compose run --rm web python manage.py migrate
docker compose run --rm web pytest -v
```

Expected: all 6 migrations apply (the new `0007`), and all 163 tests pass under their new names/paths.

- [ ] **Step 16: Commit**

```bash
git add boards/
git commit -m "Rename Card to WorkItem and /api/cards/ to /api/work-items/"
```

---

## Task 2: `item_type`, `key`, `parent` — the validated hierarchy

**Files:**
- Modify: `projects/models.py`, `boards/models.py`, `boards/serializers.py`, `boards/views.py`
- Create: `projects/migrations/0002_project_next_item_number.py`, `boards/migrations/0008_workitem_item_type_and_parent.py`, `boards/migrations/0009_backfill_work_item_keys.py`, `boards/migrations/0010_workitem_key_required.py`
- Test: `boards/tests/test_work_item_hierarchy.py`

**Interfaces:**
- Consumes: `WorkItem`, `WorkItemViewSet`, `WorkItemSerializer` (Task 1); `Project` (sub-project 1).
- Produces: `WorkItem.item_type` (one of `epic`/`story`/`task`/`bug`/`subtask`), `WorkItem.key` (e.g. `TASKY-123`, immutable, unique), `WorkItem.parent` (self FK, `related_name="children"`). `boards.serializers.hierarchy_error(item_type, parent)` — later tasks don't need this directly, but it's the single source of truth for the validation rule, mirroring `design/js/store.js`'s `hierarchyError`. `GET /api/work-items/{id}/children/`.

- [ ] **Step 1: Write the failing tests**

Create `boards/tests/test_work_item_hierarchy.py`:

```python
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
def test_retrieving_a_nonexistent_work_item_is_404(auth_client):
    """Closes a gap left open in sub-project 1 (Board had this test, Card
    never did) — a genuinely missing id must 404, distinct from the 403 a
    non-member gets for an id that exists in a project they're not in."""
    assert auth_client.get("/api/work-items/999999/").status_code == 404
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `docker compose run --rm web pytest boards/tests/test_work_item_hierarchy.py -v`
Expected: FAIL — `item_type`/`parent`/`key` aren't real fields yet, `TypeError` on `WorkItem.objects.create(item_type=...)`.

- [ ] **Step 3: Add `Project.next_item_number`**

In `projects/models.py`, add to `Project` (after `description`):

```python
    next_item_number = models.IntegerField(default=1)
```

```bash
docker compose run --rm web python manage.py makemigrations projects -n project_next_item_number
```

Expected output file: `projects/migrations/0002_project_next_item_number.py`.

- [ ] **Step 4: Add `item_type` and `parent` to `WorkItem`**

In `boards/models.py`, add to `WorkItem` (right after `class Priority`, before the `board` field):

```python
    class ItemType(models.TextChoices):
        EPIC = "epic", "Epic"
        STORY = "story", "Story"
        TASK = "task", "Task"
        BUG = "bug", "Bug"
        SUBTASK = "subtask", "Subtask"
```

Add the fields (right after `priority`):

```python
    item_type = models.CharField(max_length=10, choices=ItemType.choices, default=ItemType.TASK)
```

Add `parent` right after `assignee`:

```python
    parent = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="children"
    )
```

`key` is added separately in the next two steps, since it needs the nullable-then-required migration pattern (see Global Constraints).

```bash
docker compose run --rm web python manage.py makemigrations boards -n workitem_item_type_and_parent
```

Expected output file: `boards/migrations/0008_workitem_item_type_and_parent.py`.

- [ ] **Step 5: Add `key` as nullable, then a data migration to backfill it**

In `boards/models.py`, add `key` right after `title`:

```python
    key = models.CharField(max_length=20, null=True)
```

```bash
docker compose run --rm web python manage.py makemigrations boards -n workitem_key_nullable
```

Expected output file: a migration adding `key` (nullable, no unique constraint yet) — rename it to `0009_backfill_work_item_keys.py` is wrong; keep the auto-generated name for the `AddField`, then create a **separate** empty migration for the backfill:

```bash
docker compose run --rm web python manage.py makemigrations boards --empty -n backfill_work_item_keys
```

Expected output file: `boards/migrations/0010_backfill_work_item_keys.py` (assuming the `AddField` landed as `0009_workitem_key_nullable.py` — adjust the dependency below to match whatever name your `AddField` migration actually got). Replace the empty migration's contents with:

```python
from django.db import migrations


def backfill_keys(apps, schema_editor):
    WorkItem = apps.get_model("boards", "WorkItem")
    Project = apps.get_model("projects", "Project")

    for project in Project.objects.all():
        items = list(
            WorkItem.objects.filter(board__project=project, key__isnull=True)
            .order_by("created_at", "id")
        )
        if not items:
            continue

        counter = project.next_item_number
        for item in items:
            item.key = f"{project.key}-{counter}"
            counter += 1
        WorkItem.objects.bulk_update(items, ["key"])

        project.next_item_number = counter
        project.save(update_fields=["next_item_number"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("boards", "0009_workitem_key_nullable"),  # match your actual AddField migration name
        ("projects", "0002_project_next_item_number"),
    ]
    operations = [
        migrations.RunPython(backfill_keys, noop_reverse),
    ]
```

This mirrors `boards/migrations/0005_backfill_legacy_project.py` from sub-project 1: it's a no-op on a fresh test database (the `if not items: continue` guard), and correctly backfills a seeded dev database's pre-existing work items with real, sequential, project-scoped keys — while also advancing `next_item_number` so the very next *real* create doesn't collide with a backfilled key.

- [ ] **Step 6: Make `key` required and unique**

In `boards/models.py`, change the `key` field to:

```python
    key = models.CharField(max_length=20, unique=True)
```

```bash
docker compose run --rm web python manage.py makemigrations boards -n workitem_key_required
```

Expected output file: `boards/migrations/0011_workitem_key_required.py` (or whatever number follows your actual chain).

- [ ] **Step 7: Write the hierarchy validation and key generation**

In `boards/serializers.py`, add near the top (after the imports, before `BoardSerializer`):

```python
VALID_PARENT_TYPES = {
    WorkItem.ItemType.EPIC: [],
    WorkItem.ItemType.STORY: [WorkItem.ItemType.EPIC],
    WorkItem.ItemType.TASK: [WorkItem.ItemType.EPIC],
    WorkItem.ItemType.BUG: [WorkItem.ItemType.EPIC],
    WorkItem.ItemType.SUBTASK: [WorkItem.ItemType.STORY, WorkItem.ItemType.TASK, WorkItem.ItemType.BUG],
}


def hierarchy_error(item_type, parent):
    """None if valid, else an error message string. `parent` is a WorkItem
    instance or None. Mirrors design/js/store.js's hierarchyError exactly,
    so the prototype and the real API agree on every shape."""
    parent_type = parent.item_type if parent else None
    if parent_type is None:
        if item_type == WorkItem.ItemType.SUBTASK:
            return "A Subtask must have a parent Story, Task, or Bug."
        return None
    if parent_type not in VALID_PARENT_TYPES.get(item_type, []):
        label = dict(WorkItem.ItemType.choices)[item_type]
        article = "An" if label[0] in "AEIOU" else "A"
        return f"{article} {label} can't have that parent."
    return None
```

Add a lightweight summary serializer (used for `parent_detail` and the `children` endpoint) right before `WorkItemSerializer`:

```python
class WorkItemSummarySerializer(serializers.ModelSerializer):
    """Enough to identify and link to another work item, without pulling
    its full field set — used for parent_detail and the children list."""

    class Meta:
        model = WorkItem
        fields = ["id", "key", "title", "item_type", "status"]
```

Update `WorkItemSerializer` to:

```python
class WorkItemSerializer(serializers.ModelSerializer):
    assignee_detail = UserSerializer(source="assignee", read_only=True)
    created_by = UserSerializer(read_only=True)
    priority_label = serializers.CharField(source="get_priority_display", read_only=True)
    parent_detail = WorkItemSummarySerializer(source="parent", read_only=True)

    class Meta:
        model = WorkItem
        fields = [
            "id", "key", "board", "item_type", "title", "description",
            "status", "priority", "priority_label", "due_date",
            "assignee", "assignee_detail", "parent", "parent_detail",
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
            item_type = attrs.get("item_type") or (self.instance.item_type if self.instance else None)
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

        return attrs
```

(`item_type` stays a normal writable field on create — its *immutability after creation* is enforced in the view, in Step 8, the same way `status`/`board` already are; the serializer's `validate()` only needs to know the item's type to check hierarchy, not to guard against it changing.)

- [ ] **Step 8: Generate the key on create, extend the immutability guard, add the `children` action**

In `boards/views.py`, add `from django.db import transaction` and `from projects.models import Project` to the imports (alongside the existing `ProjectMembership` import), and import `WorkItemSummarySerializer` from `.serializers`.

Replace `WorkItemViewSet.perform_create` with:

```python
    def perform_create(self, serializer):
        board = serializer.validated_data["board"]
        status = serializer.validated_data.get("status", WorkItem.Status.TODO)
        with transaction.atomic():
            project = Project.objects.select_for_update().get(pk=board.project_id)
            key = f"{project.key}-{project.next_item_number}"
            project.next_item_number += 1
            project.save(update_fields=["next_item_number"])
            serializer.save(
                key=key,
                created_by=self.request.user,
                position=next_position(board.id, status),
            )
```

Extend the `if` condition at the top of `update()` to also cover `item_type` and `key`:

```python
        if "status" in request.data or "board" in request.data or "item_type" in request.data or "key" in request.data:
            item = self.get_object()
            if "status" in request.data and request.data["status"] != item.status:
                raise ValidationError(
                    {
                        "status": (
                            "Status cannot be changed here — "
                            "POST to /api/work-items/{id}/move/ instead."
                        )
                    }
                )
            if "board" in request.data and str(request.data["board"]) != str(item.board_id):
                raise ValidationError({"board": "Work items cannot be moved between boards."})
            if "item_type" in request.data and request.data["item_type"] != item.item_type:
                raise ValidationError({"item_type": "Type cannot be changed after creation."})
            if "key" in request.data and request.data["key"] != item.key:
                raise ValidationError({"key": "Key cannot be changed."})
```

Add the `children` action (anywhere among the other `@action` methods on `WorkItemViewSet`):

```python
    @action(detail=True, methods=["get"])
    def children(self, request, pk=None):
        item = self.get_object()
        return Response(WorkItemSummarySerializer(item.children.all(), many=True).data)
```

- [ ] **Step 9: Run the tests to confirm they pass**

Run: `docker compose run --rm web pytest boards/tests/test_work_item_hierarchy.py -v`
Expected: 14 passed.

Run: `docker compose run --rm web pytest -v`
Expected: all tests pass (163 from before + 14 new).

- [ ] **Step 10: Commit**

```bash
git add projects/ boards/
git commit -m "Add item_type, key, and validated parent hierarchy to WorkItem"
```

---

## Task 3: Components

**Files:**
- Create: `boards/migrations/00XX_component.py` (exact number follows Task 2's final migration — check `ls boards/migrations/` before naming)
- Modify: `boards/models.py`, `boards/serializers.py`, `boards/views.py`, `boards/urls.py`
- Test: `boards/tests/test_components_api.py`

**Interfaces:**
- Consumes: `Logic.canManageComponents`'s backend equivalent (this task defines it — there's no prior Python version, only `design/js/logic.js`'s), `IsProjectMember`, `ProjectMembership.Role` (sub-project 1).
- Produces: `boards.models.Component` (`project`, `name`, unique together), `WorkItem.components` (M2M). `GET/POST /api/projects/{id}/components/`, `PATCH/DELETE /api/projects/{id}/components/{id}/`.

- [ ] **Step 1: Write the failing tests**

Create `boards/tests/test_components_api.py`:

```python
import pytest

from boards.models import Board, Component, WorkItem


@pytest.fixture
def board(user, project):
    return Board.objects.create(name="Test Board", created_by=user, project=project)


@pytest.mark.django_db
def test_anonymous_callers_are_rejected(client, project):
    assert client.get(f"/api/projects/{project.id}/components/").status_code == 403


@pytest.mark.django_db
def test_owner_can_create_a_component(auth_client, project):
    response = auth_client.post(
        f"/api/projects/{project.id}/components/", {"name": "Frontend"}, content_type="application/json"
    )
    assert response.status_code == 201
    assert Component.objects.get(project=project, name="Frontend")


@pytest.mark.django_db
def test_member_cannot_create_a_component(auth_client, other_user, project):
    from projects.models import ProjectMembership

    ProjectMembership.objects.filter(project=project, user__username="alice").update(role="member")
    response = auth_client.post(
        f"/api/projects/{project.id}/components/", {"name": "Backend"}, content_type="application/json"
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_duplicate_component_name_in_the_same_project_is_rejected(auth_client, project):
    Component.objects.create(project=project, name="Frontend")
    response = auth_client.post(
        f"/api/projects/{project.id}/components/", {"name": "Frontend"}, content_type="application/json"
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_owner_can_rename_a_component(auth_client, project):
    component = Component.objects.create(project=project, name="Old name")
    response = auth_client.patch(
        f"/api/projects/{project.id}/components/{component.id}/", {"name": "New name"}, content_type="application/json"
    )
    assert response.status_code == 200
    component.refresh_from_db()
    assert component.name == "New name"


@pytest.mark.django_db
def test_owner_can_delete_a_component(auth_client, project):
    component = Component.objects.create(project=project, name="Doomed")
    assert auth_client.delete(f"/api/projects/{project.id}/components/{component.id}/").status_code == 204
    assert not Component.objects.filter(id=component.id).exists()


@pytest.mark.django_db
def test_deleting_a_component_clears_it_from_work_items_without_deleting_them(auth_client, board, project):
    component = Component.objects.create(project=project, name="Frontend")
    item = WorkItem.objects.create(board=board, title="Has a component")
    item.components.add(component)

    auth_client.delete(f"/api/projects/{project.id}/components/{component.id}/")

    item.refresh_from_db()
    assert WorkItem.objects.filter(id=item.id).exists()
    assert component.id not in item.components.values_list("id", flat=True)


@pytest.mark.django_db
def test_any_member_can_apply_an_existing_component_to_a_work_item(auth_client, board, project):
    component = Component.objects.create(project=project, name="Frontend")
    item = WorkItem.objects.create(board=board, title="Needs tagging")

    response = auth_client.patch(
        f"/api/work-items/{item.id}/", {"components": [component.id]}, content_type="application/json"
    )

    assert response.status_code == 200
    assert response.json()["components_detail"][0]["name"] == "Frontend"


@pytest.mark.django_db
def test_a_component_from_another_project_cannot_be_applied(auth_client, board, other_user):
    from projects.models import Project, ProjectMembership

    foreign_project = Project.objects.create(key="FOREIGN", name="Not Yours")
    ProjectMembership.objects.create(project=foreign_project, user=other_user, role="owner")
    foreign_component = Component.objects.create(project=foreign_project, name="Not applicable")
    item = WorkItem.objects.create(board=board, title="Item")

    response = auth_client.patch(
        f"/api/work-items/{item.id}/", {"components": [foreign_component.id]}, content_type="application/json"
    )

    assert response.status_code == 400
    assert "components" in response.json()
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `docker compose run --rm web pytest boards/tests/test_components_api.py -v`
Expected: FAIL — `ImportError` (`Component` doesn't exist yet).

- [ ] **Step 3: Add the `Component` model and `WorkItem.components`**

In `boards/models.py`, add after the `WorkItem` class:

```python
class Component(models.Model):
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="components")
    name = models.CharField(max_length=80)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["project", "name"], name="unique_component_name_per_project"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.project})"
```

Add to `WorkItem` (after `parent`):

```python
    components = models.ManyToManyField(Component, blank=True, related_name="work_items")
```

```bash
docker compose run --rm web python manage.py makemigrations boards -n component
```

Expected output file matches whatever number follows Task 2's chain — check `ls boards/migrations/` first and confirm.

- [ ] **Step 4: Add `can_manage_components`, serializers, and the components field on `WorkItemSerializer`**

In `boards/serializers.py`, add near the top (with the other module-level helpers, after `hierarchy_error`):

```python
def can_manage_components(role):
    return role in ("owner", "admin")
```

Add `ComponentSerializer` (after `BoardSerializer`, before `WorkItemSummarySerializer`):

```python
class ComponentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Component
        fields = ["id", "project", "name"]
        read_only_fields = ["project"]

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("This field may not be blank.")
        return value.strip()
```

Update the `from .models import ...` line to include `Component`. Then **replace the entire `WorkItemSerializer` class** (this supersedes Task 2's version in full — it keeps `validate_board` and the hierarchy checks inside `validate()` from Task 2 unchanged, and adds `components_detail`, the writable `components` field, and a components-project-match check at the end of `validate()`):

```python
class WorkItemSerializer(serializers.ModelSerializer):
    assignee_detail = UserSerializer(source="assignee", read_only=True)
    created_by = UserSerializer(read_only=True)
    priority_label = serializers.CharField(source="get_priority_display", read_only=True)
    parent_detail = WorkItemSummarySerializer(source="parent", read_only=True)
    components_detail = ComponentSerializer(source="components", many=True, read_only=True)

    class Meta:
        model = WorkItem
        fields = [
            "id", "key", "board", "item_type", "title", "description",
            "status", "priority", "priority_label", "due_date",
            "assignee", "assignee_detail", "parent", "parent_detail",
            "components", "components_detail",
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
            item_type = attrs.get("item_type") or (self.instance.item_type if self.instance else None)
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

        return attrs
```

- [ ] **Step 5: Add the components viewset**

In `boards/views.py`, import `Component` and `can_manage_components` alongside the existing imports, and `PermissionDenied` (already imported). Add a new viewset:

```python
class ComponentViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = ComponentSerializer
    permission_classes = [IsAuthenticated, IsProjectMember]
    pagination_class = None

    def get_project(self):
        from projects.models import Project
        return get_object_or_404(Project, pk=self.kwargs["project_pk"])

    def get_queryset(self):
        return Component.objects.filter(project_id=self.kwargs["project_pk"])

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        # IsProjectMember needs an object to check on list/create, where DRF
        # never calls check_object_permissions — the project itself stands
        # in. For patch/delete, DRF's own get_object() already calls
        # check_object_permissions() with the fetched Component instance —
        # Component.project is a real FK field, so IsProjectMember resolves
        # it correctly with no override needed there.
        if self.action in ("list", "create"):
            self.check_object_permissions(request, self.get_project())

    def perform_create(self, serializer):
        project = self.get_project()
        role = project.memberships.get(user=self.request.user).role
        if not can_manage_components(role):
            raise PermissionDenied("You don't have permission to manage components.")
        serializer.save(project=project)

    def perform_update(self, serializer):
        role = serializer.instance.project.memberships.get(user=self.request.user).role
        if not can_manage_components(role):
            raise PermissionDenied("You don't have permission to manage components.")
        serializer.save()

    def perform_destroy(self, instance):
        role = instance.project.memberships.get(user=self.request.user).role
        if not can_manage_components(role):
            raise PermissionDenied("You don't have permission to manage components.")
        instance.delete()
```

Add `from django.shortcuts import get_object_or_404` to the imports if not already present (it isn't, in this file).

- [ ] **Step 6: Wire the URL**

Components are nested under a project, unlike every other viewset in `boards/urls.py` (which are flat). Add to `boards/urls.py`:

```python
from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import BoardViewSet, CommentViewSet, ComponentViewSet, WorkItemViewSet

router = DefaultRouter()
router.register("boards", BoardViewSet, basename="board")
router.register("work-items", WorkItemViewSet, basename="work-item")
router.register("comments", CommentViewSet, basename="comment")

urlpatterns = router.urls + [
    path(
        "projects/<int:project_pk>/components/",
        ComponentViewSet.as_view({"get": "list", "post": "create"}),
        name="project-components",
    ),
    path(
        "projects/<int:project_pk>/components/<int:pk>/",
        ComponentViewSet.as_view({"patch": "partial_update", "delete": "destroy"}),
        name="project-component-detail",
    ),
]
```

- [ ] **Step 7: Run the tests to confirm they pass**

Run: `docker compose run --rm web pytest boards/tests/test_components_api.py -v`
Expected: 9 passed.

Run: `docker compose run --rm web pytest -v`
Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add boards/
git commit -m "Add Component model and management endpoints"
```

---

## Task 4: Work item linking ("relates to")

**Files:**
- Create: `boards/migrations/00XX_workitemlink.py` (check `ls boards/migrations/` for the next number)
- Modify: `boards/models.py`, `boards/serializers.py`, `boards/views.py`, `boards/urls.py`
- Test: `boards/tests/test_work_item_links_api.py`

**Interfaces:**
- Consumes: `WorkItem`, `IsProjectMember` (Tasks 1–2).
- Produces: `boards.models.WorkItemLink` (`item_a`, `item_b`, canonical `item_a.id < item_b.id` ordering). `GET/POST /api/work-items/{id}/links/`, `DELETE /api/work-item-links/{id}/`.

- [ ] **Step 1: Write the failing tests**

Create `boards/tests/test_work_item_links_api.py`:

```python
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
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `docker compose run --rm web pytest boards/tests/test_work_item_links_api.py -v`
Expected: FAIL — `ImportError` (`WorkItemLink` doesn't exist yet).

- [ ] **Step 3: Add the `WorkItemLink` model**

In `boards/models.py`, add after `Component`:

```python
class WorkItemLink(models.Model):
    """Symmetric — there is no "from"/"to" direction. item_a always holds
    the lower id, so (A, B) and (B, A) are the same row; enforced by the
    UniqueConstraint below, not just convention."""

    item_a = models.ForeignKey(WorkItem, on_delete=models.CASCADE, related_name="links_as_a")
    item_b = models.ForeignKey(WorkItem, on_delete=models.CASCADE, related_name="links_as_b")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="work_item_links_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["item_a", "item_b"], name="unique_work_item_link"),
        ]

    def __str__(self) -> str:
        return f"{self.item_a} <-> {self.item_b}"
```

```bash
docker compose run --rm web python manage.py makemigrations boards -n workitemlink
```

Expected output file matches whatever number follows Task 3's chain — check `ls boards/migrations/` first.

- [ ] **Step 4: Add the serializer**

In `boards/serializers.py`, add after `WorkItemSerializer`:

```python
class WorkItemLinkSerializer(serializers.ModelSerializer):
    item = serializers.PrimaryKeyRelatedField(queryset=WorkItem.objects.all(), write_only=True)
    item_detail = serializers.SerializerMethodField()

    class Meta:
        model = WorkItemLink
        fields = ["id", "item", "item_detail", "created_at"]

    def get_item_detail(self, obj):
        # "the other side" — resolved relative to whichever item this link
        # is being rendered for, stashed on the instance by the view.
        other = obj.item_b if obj.item_a_id == self.context["for_item_id"] else obj.item_a
        return WorkItemSummarySerializer(other).data
```

- [ ] **Step 5: Add the viewset and actions**

In `boards/views.py`, add `from django.db import models` to the top-level imports (needed for `models.Q` below — this is Django's query-expression module, unrelated to the file's existing local `from .models import Board, Comment, WorkItem` import). Import `WorkItemLink` and `WorkItemLinkSerializer` alongside the other local imports. Add these two `@action` methods to `WorkItemViewSet` (alongside `children`):

```python
    @action(detail=True, methods=["get", "post"])
    def links(self, request, pk=None):
        item = self.get_object()

        if request.method == "POST":
            serializer = WorkItemLinkSerializer(data=request.data, context={"for_item_id": item.id})
            serializer.is_valid(raise_exception=True)
            other = serializer.validated_data["item"]

            if other.id == item.id:
                raise ValidationError({"item": "An item can't be linked to itself."})
            # `other` is already the resolved WorkItem instance — the
            # PrimaryKeyRelatedField's queryset lookup during is_valid()
            # already proved it exists, so re-fetching it would be a
            # redundant query. Membership is the only thing left to check.
            self.check_object_permissions(request, other)

            if item.parent_id == other.id or other.parent_id == item.id:
                raise ValidationError({"item": "These items are already parent and child."})

            item_a, item_b = sorted([item, other], key=lambda w: w.id)
            if WorkItemLink.objects.filter(item_a=item_a, item_b=item_b).exists():
                raise ValidationError({"item": "These items are already linked."})

            link = WorkItemLink.objects.create(item_a=item_a, item_b=item_b, created_by=request.user)
            out = WorkItemLinkSerializer(link, context={"for_item_id": item.id})
            return Response(out.data, status=201)

        thread = WorkItemLink.objects.filter(
            models.Q(item_a=item) | models.Q(item_b=item)
        ).select_related("item_a", "item_b")
        return Response(
            WorkItemLinkSerializer(thread, many=True, context={"for_item_id": item.id}).data
        )
```

Add a small viewset for deletion, alongside `CommentViewSet`:

```python
class WorkItemLinkViewSet(mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """Deletion only — links are created through a work item's own /links/ endpoint."""

    serializer_class = WorkItemLinkSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return WorkItemLink.objects.select_related("item_a__board__project", "item_b__board__project")

    def check_object_permissions(self, request, obj):
        # Either side being in one of my projects is enough — the item that
        # created the link already proved membership; this just confirms
        # the caller isn't a total stranger to both.
        in_a = obj.item_a.project.memberships.filter(user=request.user).exists()
        in_b = obj.item_b.project.memberships.filter(user=request.user).exists()
        if not (in_a or in_b):
            self.permission_denied(request, message="You don't have access to this project.")
```

- [ ] **Step 6: Wire the URL**

Replace `boards/urls.py` in full (this supersedes Task 3's version — the only change is the added `router.register` line and the `WorkItemLinkViewSet` import; the two `path()` entries for components from Task 3 are unchanged):

```python
from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    BoardViewSet,
    CommentViewSet,
    ComponentViewSet,
    WorkItemLinkViewSet,
    WorkItemViewSet,
)

router = DefaultRouter()
router.register("boards", BoardViewSet, basename="board")
router.register("work-items", WorkItemViewSet, basename="work-item")
router.register("comments", CommentViewSet, basename="comment")
router.register("work-item-links", WorkItemLinkViewSet, basename="work-item-link")

urlpatterns = router.urls + [
    path(
        "projects/<int:project_pk>/components/",
        ComponentViewSet.as_view({"get": "list", "post": "create"}),
        name="project-components",
    ),
    path(
        "projects/<int:project_pk>/components/<int:pk>/",
        ComponentViewSet.as_view({"patch": "partial_update", "delete": "destroy"}),
        name="project-component-detail",
    ),
]
```

- [ ] **Step 7: Run the tests to confirm they pass**

Run: `docker compose run --rm web pytest boards/tests/test_work_item_links_api.py -v`
Expected: 7 passed.

Run: `docker compose run --rm web pytest -v`
Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add boards/
git commit -m "Add WorkItemLink model and 'relates to' endpoints"
```

---

## Task 5: Documentation and final regression

**Files:**
- Modify: `docs/api.md`

**Interfaces:**
- None — documentation only.

- [ ] **Step 1: Update `docs/api.md`**

Rename the `## Cards` section to `## Work Items`, updating every path from `/api/cards/` to `/api/work-items/` and `/api/boards/{id}/cards/` to `/api/boards/{id}/work-items/`. Add rows for the new fields (`item_type`, `key`, `parent`, `components`) and the new sub-resources:

```markdown
## Work Items
| Method | Path | Notes |
|---|---|---|
| GET | `/api/work-items/` | every work item on a board in a project I'm a member of |
| POST | `/api/work-items/` | `{board, item_type, title, description?, status?, priority?, due_date?, assignee?, parent?, components?}` |
| GET/PUT/PATCH/DELETE | `/api/work-items/{id}/` | `key`, `item_type`, `position` are immutable; `status`/`board` unchanged from before |
| POST | `/api/work-items/{id}/move/` | unchanged — the drag-and-drop endpoint |
| GET | `/api/boards/{id}/work-items/` | every work item on that board |
| GET | `/api/work-items/{id}/children/` | direct children only (not grandchildren) |
| GET/POST | `/api/work-items/{id}/links/` | list / create a "relates to" link; POST body is `{item: <other work item id>}` |

`item_type` is one of `epic`, `story`, `task`, `bug`, `subtask` — fixed for every project. `key` (e.g. `TASKY-123`) is generated on create from a per-project counter shared across every type and board, and can never be changed afterward. `parent` must be an Epic for a Story/Task/Bug, must be a Story/Task/Bug for a Subtask (required, not optional), can never be set on an Epic, and must be on the same board as the child — violating any of these is a `400` naming `parent`. Deleting a work item clears its children's `parent` rather than deleting them.

## Components
| Method | Path | Notes |
|---|---|---|
| GET/POST | `/api/projects/{id}/components/` | POST is Owner/Admin only |
| PATCH/DELETE | `/api/projects/{id}/components/{id}/` | Owner/Admin only |

Any project member can apply an existing component to a work item via `PATCH /api/work-items/{id}/ {"components": [...]}"` — a component from a different project than the work item's is rejected with `400`.

## Work Item Links
| Method | Path | Notes |
|---|---|---|
| DELETE | `/api/work-item-links/{id}/` | removes the link from both sides |

See `GET/POST /api/work-items/{id}/links/` above for listing/creating. Self-links, duplicate links, and linking two items already in a parent/child relationship are all rejected with `400`.
```

- [ ] **Step 2: Full regression run**

Run: `docker compose run --rm web pytest -v`
Expected: every test passes (163 pre-existing + all tests added in Tasks 1–4).

Run: `docker compose run --rm web python manage.py check`
Expected: `System check identified no issues.`

- [ ] **Step 3: Commit**

```bash
git add docs/api.md
git commit -m "Document work items, components, and links"
```

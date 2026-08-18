# Custom Fields & Screens Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the production Django/DRF backend for Tasky's Custom Fields & Screens feature (sub-project 2b of 13) — global `CustomField`/`Screen` definitions any project Owner can manage, per-project-per-item-type `Screen` assignment, and a validated `custom_fields` read/write surface on `WorkItem`.

**Architecture:** Six new models in the existing `boards` app (`CustomField`, `FieldOption`, `Screen`, `ScreenField`, `ProjectScreenAssignment`, `WorkItemFieldValue`) — nothing here is project-scoped except the assignment row itself, matching the spec's "fields and screens are global" decision. `WorkItemSerializer` gains a `custom_fields` write-only `DictField` plus a hand-built `custom_fields` key in `to_representation()`; all cross-field validation (screen resolution, allowed-field check, required check, per-type value check) lives in new functions in `boards/services.py`, mirroring `design/js/store.js`'s `customFieldsError`/`applyCustomFields`/`Logic.fieldValueError` line for line so the prototype and the real API agree on every message.

**Tech Stack:** Django 5.2, DRF 3.16, MySQL, pytest-django. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-18-tasky-custom-fields-screens-design.md` (signed off 2026-08-18; the `design/` prototype it argues from was signed off the same day)

## Global Constraints

- **Role vocabulary is `owner` / `admin` / `member`** (lowercase) — unchanged from sub-project 1.
- **A non-member touching anything project-scoped gets `403`, not `404`; a genuinely missing id still `404`s** — `IsProjectMember`'s existing object-level pattern, reused verbatim for the one project-scoped endpoint this plan adds (`/api/projects/{id}/screen-assignments/`). `CustomField`/`Screen`/`FieldOption`/`ScreenField` are global, not project-scoped, so they use `IsAuthenticated` only, with the "Owner of any project" check done explicitly in each `perform_create`/`perform_update`/`perform_destroy` — there is no object to be "a member of."
- **`field_type` is immutable after creation**, rejected with `400` via the same raw-`request.data` inspection idiom `WorkItemViewSet.update()` already uses for `status`/`board`/`item_type`/`key` — never via the serializer, which never sees the rejected write.
- **Unauthenticated request → `403`, never `401`** (existing site-wide convention, unchanged).
- **A guard-type `400` with no single offending field uses `{"detail": "..."}`** — the pattern already established in `projects/views.py`'s `remove_member`/`transfer_ownership`. A `custom_fields` error always uses the key `"custom_fields"` specifically, per the spec's error table.
- **Every new migration is a plain additive `CreateModel`** — nothing in this plan touches an existing column, so none of them need the nullable → backfill → required dance sub-project 2a's `key` migration required.

---

## Task 1: `CustomField` and `FieldOption`

**Files:**
- Create: `boards/migrations/0014_custom_field_and_option.py`
- Modify: `boards/models.py`, `boards/serializers.py`, `boards/views.py`, `boards/urls.py`
- Test: `boards/tests/test_custom_fields_api.py`

**Interfaces:**
- Consumes: `IsAuthenticated`, the raw-`request.data` immutability-check idiom from `WorkItemViewSet.update()`.
- Produces: `boards.models.CustomField` (`name`, `field_type`, `created_by`, `created_at`), `boards.models.FieldOption` (`field`, `label`, `position`). `boards.serializers.user_can_manage_definitions(user) -> bool`, `CustomFieldSerializer`, `FieldOptionSerializer`. `GET/POST /api/fields/`, `GET/PATCH/DELETE /api/fields/{id}/`, `POST /api/fields/{field_id}/options/`, `PATCH/DELETE /api/fields/{field_id}/options/{id}/`. Later tasks import `CustomField`, `FieldOption`, and `user_can_manage_definitions` from here.

- [ ] **Step 1: Write the failing tests**

Create `boards/tests/test_custom_fields_api.py`:

```python
import pytest

from boards.models import CustomField, FieldOption
from projects.models import ProjectMembership


@pytest.mark.django_db
def test_anonymous_callers_are_rejected(client):
    assert client.get("/api/fields/").status_code == 403


@pytest.mark.django_db
def test_owner_of_any_project_can_create_a_field(auth_client, project, user):
    response = auth_client.post(
        "/api/fields/", {"name": "Story Points", "field_type": "number"}, content_type="application/json"
    )
    assert response.status_code == 201
    field = CustomField.objects.get(name="Story Points")
    assert field.field_type == "number"
    assert field.created_by == user


@pytest.mark.django_db
def test_a_plain_member_cannot_create_a_field(auth_client, project):
    ProjectMembership.objects.filter(project=project, user__username="alice").update(role="member")
    response = auth_client.post(
        "/api/fields/", {"name": "Story Points", "field_type": "number"}, content_type="application/json"
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_being_owner_of_any_project_is_enough_not_necessarily_a_specific_one(auth_client, user):
    """No `project` fixture here on purpose — CustomField isn't scoped to
    any project, so this proves ownership of *some* unrelated project is
    what the check actually keys on, not membership in a project the
    request happens to reference (there isn't one)."""
    from projects.models import Project, ProjectMembership

    somewhere = Project.objects.create(key="SOMEWHERE", name="Somewhere")
    ProjectMembership.objects.create(project=somewhere, user=user, role="owner")

    response = auth_client.post(
        "/api/fields/", {"name": "Severity", "field_type": "select"}, content_type="application/json"
    )
    assert response.status_code == 201


@pytest.mark.django_db
def test_duplicate_field_name_is_rejected_case_insensitively(auth_client, project):
    CustomField.objects.create(name="Story Points", field_type="number", created_by=None)
    response = auth_client.post(
        "/api/fields/", {"name": "story points", "field_type": "number"}, content_type="application/json"
    )
    assert response.status_code == 400
    assert "name" in response.json()


@pytest.mark.django_db
def test_owner_can_rename_a_field(auth_client, project):
    field = CustomField.objects.create(name="Old name", field_type="text_short", created_by=None)
    response = auth_client.patch(f"/api/fields/{field.id}/", {"name": "New name"}, content_type="application/json")
    assert response.status_code == 200
    field.refresh_from_db()
    assert field.name == "New name"


@pytest.mark.django_db
def test_field_type_cannot_be_changed(auth_client, project):
    field = CustomField.objects.create(name="Points", field_type="number", created_by=None)
    response = auth_client.patch(
        f"/api/fields/{field.id}/", {"field_type": "text_short"}, content_type="application/json"
    )
    assert response.status_code == 400
    assert "field_type" in response.json()
    field.refresh_from_db()
    assert field.field_type == "number"


@pytest.mark.django_db
def test_patching_field_type_to_its_own_current_value_is_a_no_op(auth_client, project):
    field = CustomField.objects.create(name="Points", field_type="number", created_by=None)
    response = auth_client.patch(
        f"/api/fields/{field.id}/", {"field_type": "number", "name": "Story Points"}, content_type="application/json"
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_owner_can_delete_an_unused_field(auth_client, project):
    """This task's `CustomFieldViewSet.perform_destroy` has no in-use guard
    yet — `ScreenField` doesn't exist until Task 2, which is also where the
    "still on a screen, rejected" guard and its test get added."""
    field = CustomField.objects.create(name="Doomed", field_type="text_short", created_by=None)
    assert auth_client.delete(f"/api/fields/{field.id}/").status_code == 204
    assert not CustomField.objects.filter(id=field.id).exists()


@pytest.mark.django_db
def test_adding_an_option_to_a_select_field(auth_client, project):
    field = CustomField.objects.create(name="Severity", field_type="select", created_by=None)
    response = auth_client.post(
        f"/api/fields/{field.id}/options/", {"label": "High"}, content_type="application/json"
    )
    assert response.status_code == 201
    option = FieldOption.objects.get(field=field, label="High")
    assert option.position == 0


@pytest.mark.django_db
def test_adding_an_option_to_a_non_option_field_is_rejected(auth_client, project):
    field = CustomField.objects.create(name="Points", field_type="number", created_by=None)
    response = auth_client.post(
        f"/api/fields/{field.id}/options/", {"label": "High"}, content_type="application/json"
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_duplicate_option_label_on_the_same_field_is_rejected(auth_client, project):
    field = CustomField.objects.create(name="Severity", field_type="select", created_by=None)
    FieldOption.objects.create(field=field, label="High", position=0)
    response = auth_client.post(
        f"/api/fields/{field.id}/options/", {"label": "high"}, content_type="application/json"
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_reordering_options(auth_client, project):
    field = CustomField.objects.create(name="Severity", field_type="select", created_by=None)
    low = FieldOption.objects.create(field=field, label="Low", position=0)
    high = FieldOption.objects.create(field=field, label="High", position=1)

    response = auth_client.patch(
        f"/api/fields/{field.id}/options/{high.id}/", {"position": 0}, content_type="application/json"
    )
    assert response.status_code == 200
    low.refresh_from_db()
    high.refresh_from_db()
    assert (high.position, low.position) == (0, 1)


@pytest.mark.django_db
def test_deleting_an_unused_option_renumbers_the_rest(auth_client, project):
    field = CustomField.objects.create(name="Severity", field_type="select", created_by=None)
    low = FieldOption.objects.create(field=field, label="Low", position=0)
    mid = FieldOption.objects.create(field=field, label="Mid", position=1)
    high = FieldOption.objects.create(field=field, label="High", position=2)

    response = auth_client.delete(f"/api/fields/{field.id}/options/{low.id}/")
    assert response.status_code == 204
    mid.refresh_from_db()
    high.refresh_from_db()
    assert (mid.position, high.position) == (0, 1)
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `docker compose run --rm web pytest boards/tests/test_custom_fields_api.py -v`
Expected: FAIL — `ImportError` (`CustomField` doesn't exist yet).

- [ ] **Step 3: Add the models**

In `boards/models.py`, add after the `Component` class:

```python
class CustomField(models.Model):
    class FieldType(models.TextChoices):
        TEXT_SHORT = "text_short", "Short text"
        TEXT_LONG = "text_long", "Long text"
        NUMBER = "number", "Number"
        DATE = "date", "Date"
        SELECT = "select", "Select"
        MULTISELECT = "multiselect", "Multi-select"
        CHECKBOX = "checkbox", "Checkbox"
        USER_PICKER = "user_picker", "User picker"

    OPTION_TYPES = (FieldType.SELECT, FieldType.MULTISELECT)

    name = models.CharField(max_length=80, unique=True)
    field_type = models.CharField(max_length=20, choices=FieldType.choices)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="custom_fields_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    @property
    def has_options(self) -> bool:
        return self.field_type in self.OPTION_TYPES


class FieldOption(models.Model):
    field = models.ForeignKey(CustomField, on_delete=models.CASCADE, related_name="options")
    label = models.CharField(max_length=120)
    position = models.IntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(fields=["field", "label"], name="unique_option_label_per_field"),
        ]

    def __str__(self) -> str:
        return f"{self.label} ({self.field})"
```

```bash
docker compose run --rm web python manage.py makemigrations boards -n custom_field_and_option
```

Confirm the generated file is named `boards/migrations/0014_custom_field_and_option.py` (it follows `0013_workitemlink.py`); if `makemigrations` names it differently, rename it to match.

- [ ] **Step 4: Add the permission helper and serializers**

In `boards/serializers.py`, add near `can_manage_components`:

```python
def user_can_manage_definitions(user):
    from projects.models import ProjectMembership

    return ProjectMembership.objects.filter(user=user, role="owner").exists()
```

Update the `from .models import ...` line to include `CustomField, FieldOption`. Add, after `ComponentSerializer`:

```python
class FieldOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FieldOption
        fields = ["id", "field", "label", "position"]
        read_only_fields = ["field", "position"]

    def validate_label(self, value):
        clean = value.strip()
        if not clean:
            raise serializers.ValidationError("This field may not be blank.")
        return clean


class CustomFieldSerializer(serializers.ModelSerializer):
    options = FieldOptionSerializer(many=True, read_only=True)
    created_by = UserSerializer(read_only=True)

    class Meta:
        model = CustomField
        fields = ["id", "name", "field_type", "options", "created_by", "created_at"]
        read_only_fields = ["created_by", "created_at"]

    def validate_name(self, value):
        clean = value.strip()
        if not clean:
            raise serializers.ValidationError("This field may not be blank.")
        qs = CustomField.objects.filter(name__iexact=clean)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(f'"{clean}" already exists.')
        return clean
```

- [ ] **Step 5: Add the viewsets**

In `boards/views.py`, update the `from .models import ...` line to include `CustomField, FieldOption`, the `from .serializers import (...)` block to include `CustomFieldSerializer, FieldOptionSerializer, user_can_manage_definitions`, and add:

```python
class CustomFieldViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = CustomFieldSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    queryset = CustomField.objects.prefetch_related("options").all()

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if "field_type" in request.data and request.data["field_type"] != instance.field_type:
            raise ValidationError({"field_type": "A field's type can't be changed after it's created."})
        return super().update(request, *args, **kwargs)

    def perform_create(self, serializer):
        if not user_can_manage_definitions(self.request.user):
            raise PermissionDenied(
                "Only a project Owner can manage custom fields. You're not an Owner of any project."
            )
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        if not user_can_manage_definitions(self.request.user):
            raise PermissionDenied(
                "Only a project Owner can manage custom fields. You're not an Owner of any project."
            )
        serializer.save()

    def perform_destroy(self, instance):
        # This is deliberately unguarded — `ScreenField` doesn't exist until
        # Task 2, so there's nothing to check a field's usage against yet.
        # Task 2 replaces this method with the real "still on a screen"
        # guard once `ScreenField` exists.
        if not user_can_manage_definitions(self.request.user):
            raise PermissionDenied(
                "Only a project Owner can manage custom fields. You're not an Owner of any project."
            )
        instance.delete()


class FieldOptionViewSet(viewsets.ModelViewSet):
    http_method_names = ["post", "patch", "delete"]
    serializer_class = FieldOptionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_field(self):
        return get_object_or_404(CustomField, pk=self.kwargs["field_pk"])

    def get_queryset(self):
        return FieldOption.objects.filter(field_id=self.kwargs["field_pk"])

    def perform_create(self, serializer):
        if not user_can_manage_definitions(self.request.user):
            raise PermissionDenied(
                "Only a project Owner can manage custom fields. You're not an Owner of any project."
            )
        field = self.get_field()
        if not field.has_options:
            raise ValidationError(
                {
                    "detail": (
                        f'Only Select and Multi-select fields have options — '
                        f'"{field.name}" is a {field.get_field_type_display()}.'
                    )
                }
            )
        label = serializer.validated_data["label"]
        if FieldOption.objects.filter(field=field, label__iexact=label).exists():
            raise ValidationError({"label": f'"{label}" is already an option.'})
        position = FieldOption.objects.filter(field=field).count()
        serializer.save(field=field, position=position)

    def perform_update(self, serializer):
        if not user_can_manage_definitions(self.request.user):
            raise PermissionDenied(
                "Only a project Owner can manage custom fields. You're not an Owner of any project."
            )
        instance = serializer.instance
        label = serializer.validated_data.get("label")
        if label and FieldOption.objects.filter(field=instance.field, label__iexact=label).exclude(pk=instance.pk).exists():
            raise ValidationError({"label": f'"{label}" is already an option.'})
        serializer.save()
        if "position" in self.request.data:
            self._reposition(instance)

    def _reposition(self, instance):
        target = max(0, int(self.request.data["position"]))
        siblings = list(FieldOption.objects.filter(field=instance.field).exclude(pk=instance.pk).order_by("position", "id"))
        target = min(target, len(siblings))
        siblings.insert(target, instance)
        for index, option in enumerate(siblings):
            if option.position != index:
                option.position = index
                option.save(update_fields=["position"])

    def perform_destroy(self, instance):
        # Unguarded for the same reason CustomFieldViewSet's was in this
        # same task: WorkItemFieldValue doesn't exist until Task 4, so
        # there's nothing to check an option's usage against yet. Task 4
        # replaces this method with the real "still chosen" guard.
        if not user_can_manage_definitions(self.request.user):
            raise PermissionDenied(
                "Only a project Owner can manage custom fields. You're not an Owner of any project."
            )
        field = instance.field
        instance.delete()
        siblings = list(FieldOption.objects.filter(field=field).order_by("position", "id"))
        for index, option in enumerate(siblings):
            if option.position != index:
                option.position = index
                option.save(update_fields=["position"])
```

- [ ] **Step 6: Wire the URLs**

In `boards/urls.py`, update the import to include `CustomFieldViewSet, FieldOptionViewSet`, register `router.register("fields", CustomFieldViewSet, basename="custom-field")`, and add to the `urlpatterns` list (alongside the existing component paths):

```python
    path(
        "fields/<int:field_pk>/options/",
        FieldOptionViewSet.as_view({"post": "create"}),
        name="field-options",
    ),
    path(
        "fields/<int:field_pk>/options/<int:pk>/",
        FieldOptionViewSet.as_view({"patch": "partial_update", "delete": "destroy"}),
        name="field-option-detail",
    ),
```

- [ ] **Step 7: Run the tests to confirm they pass**

Run: `docker compose run --rm web pytest boards/tests/test_custom_fields_api.py -v`
Expected: 14 passed.

Run: `docker compose run --rm web pytest -v`
Expected: all tests pass (209 total).

- [ ] **Step 8: Commit**

```bash
git add boards/
git commit -m "Add CustomField and FieldOption models and endpoints"
```

---

## Task 2: `Screen` and `ScreenField`, and the real `CustomField` delete guard

**Files:**
- Create: `boards/migrations/0015_screen_and_screen_field.py`
- Modify: `boards/models.py`, `boards/serializers.py`, `boards/views.py`, `boards/urls.py`
- Test: `boards/tests/test_screens_api.py`

**Interfaces:**
- Consumes: `user_can_manage_definitions` (Task 1), `CustomFieldSerializer` (Task 1).
- Produces: `boards.models.Screen` (`name`), `boards.models.ScreenField` (`screen`, `field`, `position`, `required`). `ScreenSerializer`, `ScreenFieldSerializer`. `GET/POST /api/screens/`, `GET/PATCH/DELETE /api/screens/{id}/`, `POST /api/screens/{screen_id}/fields/`, `PATCH/DELETE /api/screens/{screen_id}/fields/{id}/`. Later tasks import `Screen`, `ScreenField` from here; Task 3 reads `ScreenField` rows to resolve a screen's field list, Task 4 reads them for `custom_fields` validation.

- [ ] **Step 1: Write the failing tests**

Create `boards/tests/test_screens_api.py`:

```python
import pytest

from boards.models import CustomField, Screen, ScreenField


@pytest.mark.django_db
def test_anonymous_callers_are_rejected(client):
    assert client.get("/api/screens/").status_code == 403


@pytest.mark.django_db
def test_owner_can_create_a_screen(auth_client, project):
    response = auth_client.post("/api/screens/", {"name": "Bug screen"}, content_type="application/json")
    assert response.status_code == 201
    assert Screen.objects.filter(name="Bug screen").exists()


@pytest.mark.django_db
def test_a_plain_member_cannot_create_a_screen(auth_client, project):
    from projects.models import ProjectMembership

    ProjectMembership.objects.filter(project=project, user__username="alice").update(role="member")
    response = auth_client.post("/api/screens/", {"name": "Bug screen"}, content_type="application/json")
    assert response.status_code == 403


@pytest.mark.django_db
def test_duplicate_screen_name_is_rejected(auth_client, project):
    Screen.objects.create(name="Bug screen")
    response = auth_client.post("/api/screens/", {"name": "bug screen"}, content_type="application/json")
    assert response.status_code == 400


@pytest.mark.django_db
def test_owner_can_rename_a_screen(auth_client, project):
    screen = Screen.objects.create(name="Old name")
    response = auth_client.patch(f"/api/screens/{screen.id}/", {"name": "New name"}, content_type="application/json")
    assert response.status_code == 200
    screen.refresh_from_db()
    assert screen.name == "New name"


@pytest.mark.django_db
def test_owner_can_delete_a_screen(auth_client, project):
    """This task's `ScreenViewSet.perform_destroy` has no assignment guard
    yet — `ProjectScreenAssignment` doesn't exist until Task 3, which is
    also where the "still assigned, rejected" guard and its test get added,
    mirroring how Task 1's `CustomFieldViewSet.perform_destroy` is
    unguarded until Task 2 adds `ScreenField`."""
    screen = Screen.objects.create(name="Doomed")
    assert auth_client.delete(f"/api/screens/{screen.id}/").status_code == 204


@pytest.mark.django_db
def test_adding_a_field_to_a_screen(auth_client, project):
    screen = Screen.objects.create(name="Bug screen")
    field = CustomField.objects.create(name="Severity", field_type="select", created_by=None)

    response = auth_client.post(
        f"/api/screens/{screen.id}/fields/", {"field": field.id}, content_type="application/json"
    )
    assert response.status_code == 201
    row = ScreenField.objects.get(screen=screen, field=field)
    assert row.position == 0
    assert row.required is False


@pytest.mark.django_db
def test_adding_the_same_field_twice_is_rejected(auth_client, project):
    screen = Screen.objects.create(name="Bug screen")
    field = CustomField.objects.create(name="Severity", field_type="select", created_by=None)
    ScreenField.objects.create(screen=screen, field=field, position=0)

    response = auth_client.post(
        f"/api/screens/{screen.id}/fields/", {"field": field.id}, content_type="application/json"
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_toggling_required_on_a_screen_field(auth_client, project):
    screen = Screen.objects.create(name="Bug screen")
    field = CustomField.objects.create(name="Severity", field_type="select", created_by=None)
    row = ScreenField.objects.create(screen=screen, field=field, position=0)

    response = auth_client.patch(
        f"/api/screens/{screen.id}/fields/{row.id}/", {"required": True}, content_type="application/json"
    )
    assert response.status_code == 200
    row.refresh_from_db()
    assert row.required is True


@pytest.mark.django_db
def test_the_same_field_can_be_required_on_one_screen_and_optional_on_another(auth_client, project):
    field = CustomField.objects.create(name="Severity", field_type="select", created_by=None)
    screen_a = Screen.objects.create(name="A")
    screen_b = Screen.objects.create(name="B")
    row_a = ScreenField.objects.create(screen=screen_a, field=field, position=0, required=True)
    row_b = ScreenField.objects.create(screen=screen_b, field=field, position=0, required=False)

    row_a.refresh_from_db()
    row_b.refresh_from_db()
    assert row_a.required is True
    assert row_b.required is False


@pytest.mark.django_db
def test_reordering_screen_fields(auth_client, project):
    screen = Screen.objects.create(name="Bug screen")
    field_a = CustomField.objects.create(name="A", field_type="text_short", created_by=None)
    field_b = CustomField.objects.create(name="B", field_type="text_short", created_by=None)
    row_a = ScreenField.objects.create(screen=screen, field=field_a, position=0)
    row_b = ScreenField.objects.create(screen=screen, field=field_b, position=1)

    response = auth_client.patch(
        f"/api/screens/{screen.id}/fields/{row_b.id}/", {"position": 0}, content_type="application/json"
    )
    assert response.status_code == 200
    row_a.refresh_from_db()
    row_b.refresh_from_db()
    assert (row_b.position, row_a.position) == (0, 1)


@pytest.mark.django_db
def test_removing_a_field_from_a_screen_renumbers_the_rest(auth_client, project):
    screen = Screen.objects.create(name="Bug screen")
    field_a = CustomField.objects.create(name="A", field_type="text_short", created_by=None)
    field_b = CustomField.objects.create(name="B", field_type="text_short", created_by=None)
    field_c = CustomField.objects.create(name="C", field_type="text_short", created_by=None)
    row_a = ScreenField.objects.create(screen=screen, field=field_a, position=0)
    row_b = ScreenField.objects.create(screen=screen, field=field_b, position=1)
    row_c = ScreenField.objects.create(screen=screen, field=field_c, position=2)

    response = auth_client.delete(f"/api/screens/{screen.id}/fields/{row_a.id}/")
    assert response.status_code == 204
    row_b.refresh_from_db()
    row_c.refresh_from_db()
    assert (row_b.position, row_c.position) == (0, 1)


@pytest.mark.django_db
def test_getting_a_screen_includes_its_ordered_fields(auth_client, project):
    screen = Screen.objects.create(name="Bug screen")
    field = CustomField.objects.create(name="Severity", field_type="select", created_by=None)
    ScreenField.objects.create(screen=screen, field=field, position=0, required=True)

    response = auth_client.get(f"/api/screens/{screen.id}/")
    assert response.status_code == 200
    body = response.json()
    assert body["fields"][0]["field_detail"]["name"] == "Severity"
    assert body["fields"][0]["required"] is True


@pytest.mark.django_db
def test_deleting_a_field_still_on_a_screen_is_rejected(auth_client, project):
    """The real guard, superseding Task 1's placeholder now that ScreenField exists."""
    field = CustomField.objects.create(name="In use", field_type="text_short", created_by=None)
    screen = Screen.objects.create(name="Bug screen")
    ScreenField.objects.create(screen=screen, field=field, position=0)

    response = auth_client.delete(f"/api/fields/{field.id}/")
    assert response.status_code == 400
    assert CustomField.objects.filter(id=field.id).exists()
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `docker compose run --rm web pytest boards/tests/test_screens_api.py -v`
Expected: FAIL — `ImportError` (`Screen` doesn't exist yet).

- [ ] **Step 3: Add the models**

In `boards/models.py`, add after `FieldOption`:

```python
class Screen(models.Model):
    name = models.CharField(max_length=80, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class ScreenField(models.Model):
    screen = models.ForeignKey(Screen, on_delete=models.CASCADE, related_name="screen_fields")
    field = models.ForeignKey(CustomField, on_delete=models.CASCADE, related_name="screen_fields")
    position = models.IntegerField(default=0)
    required = models.BooleanField(default=False)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(fields=["screen", "field"], name="unique_field_per_screen"),
        ]

    def __str__(self) -> str:
        return f"{self.field} on {self.screen}"
```

```bash
docker compose run --rm web python manage.py makemigrations boards -n screen_and_screen_field
```

Confirm the generated file is `boards/migrations/0015_screen_and_screen_field.py`.

- [ ] **Step 4: Add the serializers**

In `boards/serializers.py`, update the `from .models import ...` line to include `Screen, ScreenField`. Add, after `CustomFieldSerializer`:

```python
class ScreenFieldSerializer(serializers.ModelSerializer):
    field_detail = CustomFieldSerializer(source="field", read_only=True)

    class Meta:
        model = ScreenField
        fields = ["id", "field", "field_detail", "position", "required"]
        read_only_fields = ["position"]


class ScreenSerializer(serializers.ModelSerializer):
    fields = ScreenFieldSerializer(source="screen_fields", many=True, read_only=True)

    class Meta:
        model = Screen
        fields = ["id", "name", "fields"]

    def validate_name(self, value):
        clean = value.strip()
        if not clean:
            raise serializers.ValidationError("This field may not be blank.")
        qs = Screen.objects.filter(name__iexact=clean)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(f'"{clean}" already exists.')
        return clean
```

- [ ] **Step 5: Add the viewsets, and fix `CustomFieldViewSet.perform_destroy`**

In `boards/views.py`, update the `from .models import ...` line to include `Screen, ScreenField` (not `ProjectScreenAssignment` — that model doesn't exist until Task 3), and the `.serializers import (...)` block to include `ScreenSerializer, ScreenFieldSerializer`.

Replace `CustomFieldViewSet.perform_destroy` (the Task 1 placeholder) with the real guard:

```python
    def perform_destroy(self, instance):
        if not user_can_manage_definitions(self.request.user):
            raise PermissionDenied(
                "Only a project Owner can manage custom fields. You're not an Owner of any project."
            )
        screen_names = list(
            ScreenField.objects.filter(field=instance).values_list("screen__name", flat=True).distinct()
        )
        if screen_names:
            noun = "that screen" if len(screen_names) == 1 else "those screens"
            raise ValidationError(
                {"detail": f'"{instance.name}" is still on {", ".join(screen_names)}. Remove it from {noun} first.'}
            )
        instance.delete()
```

Add the two new viewsets after `FieldOptionViewSet`:

```python
class ScreenViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete"]
    serializer_class = ScreenSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    queryset = Screen.objects.prefetch_related("screen_fields__field__options").all()

    def perform_create(self, serializer):
        if not user_can_manage_definitions(self.request.user):
            raise PermissionDenied(
                "Only a project Owner can manage custom fields. You're not an Owner of any project."
            )
        serializer.save()

    def perform_update(self, serializer):
        if not user_can_manage_definitions(self.request.user):
            raise PermissionDenied(
                "Only a project Owner can manage custom fields. You're not an Owner of any project."
            )
        serializer.save()

    def perform_destroy(self, instance):
        # Unguarded for the same reason CustomFieldViewSet's was in Task 1:
        # ProjectScreenAssignment doesn't exist until Task 3, so there's
        # nothing to check a screen's assignment usage against yet. Task 3
        # replaces this method with the real "still assigned" guard.
        if not user_can_manage_definitions(self.request.user):
            raise PermissionDenied(
                "Only a project Owner can manage custom fields. You're not an Owner of any project."
            )
        instance.delete()


class ScreenFieldViewSet(viewsets.ModelViewSet):
    http_method_names = ["post", "patch", "delete"]
    serializer_class = ScreenFieldSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_screen(self):
        return get_object_or_404(Screen, pk=self.kwargs["screen_pk"])

    def get_queryset(self):
        return ScreenField.objects.filter(screen_id=self.kwargs["screen_pk"])

    def perform_create(self, serializer):
        if not user_can_manage_definitions(self.request.user):
            raise PermissionDenied(
                "Only a project Owner can manage custom fields. You're not an Owner of any project."
            )
        screen = self.get_screen()
        field = serializer.validated_data["field"]
        if ScreenField.objects.filter(screen=screen, field=field).exists():
            raise ValidationError({"field": f'"{field.name}" is already on this screen.'})
        position = ScreenField.objects.filter(screen=screen).count()
        serializer.save(screen=screen, position=position)

    def perform_update(self, serializer):
        if not user_can_manage_definitions(self.request.user):
            raise PermissionDenied(
                "Only a project Owner can manage custom fields. You're not an Owner of any project."
            )
        serializer.save()
        if "position" in self.request.data:
            self._reposition(serializer.instance)

    def _reposition(self, instance):
        target = max(0, int(self.request.data["position"]))
        siblings = list(
            ScreenField.objects.filter(screen=instance.screen).exclude(pk=instance.pk).order_by("position", "id")
        )
        target = min(target, len(siblings))
        siblings.insert(target, instance)
        for index, row in enumerate(siblings):
            if row.position != index:
                row.position = index
                row.save(update_fields=["position"])

    def perform_destroy(self, instance):
        if not user_can_manage_definitions(self.request.user):
            raise PermissionDenied(
                "Only a project Owner can manage custom fields. You're not an Owner of any project."
            )
        screen = instance.screen
        instance.delete()
        siblings = list(ScreenField.objects.filter(screen=screen).order_by("position", "id"))
        for index, row in enumerate(siblings):
            if row.position != index:
                row.position = index
                row.save(update_fields=["position"])
```

- [ ] **Step 6: Wire the URLs**

In `boards/urls.py`, update the import to include `ScreenFieldViewSet, ScreenViewSet`, register `router.register("screens", ScreenViewSet, basename="screen")`, and add:

```python
    path(
        "screens/<int:screen_pk>/fields/",
        ScreenFieldViewSet.as_view({"post": "create"}),
        name="screen-fields",
    ),
    path(
        "screens/<int:screen_pk>/fields/<int:pk>/",
        ScreenFieldViewSet.as_view({"patch": "partial_update", "delete": "destroy"}),
        name="screen-field-detail",
    ),
```

- [ ] **Step 7: Run the tests to confirm they pass**

Run: `docker compose run --rm web pytest boards/tests/test_screens_api.py boards/tests/test_custom_fields_api.py -v`
Expected: 14 + 14 = 28 passed.

Run: `docker compose run --rm web pytest -v`
Expected: all tests pass (223 total).

- [ ] **Step 8: Commit**

```bash
git add boards/
git commit -m "Add Screen and ScreenField models and endpoints"
```

---

## Task 3: `ProjectScreenAssignment`

**Files:**
- Create: `boards/migrations/0016_project_screen_assignment.py`
- Modify: `boards/models.py`, `boards/views.py`, `boards/urls.py`
- Test: `boards/tests/test_screen_assignments_api.py`

**Interfaces:**
- Consumes: `IsProjectMember`, `can_manage_components`-style role check (Task 2's `Screen`).
- Produces: `boards.models.ProjectScreenAssignment` (`project`, `item_type`, `screen`; unique together on `(project, item_type)`). `boards.serializers.can_manage_screen_assignments(role) -> bool`. `GET/PUT /api/projects/{id}/screen-assignments/` — both return/accept `{"epic": <screen id or null>, "story": ..., "task": ..., "bug": ..., "subtask": ...}`. Also replaces Task 2's unguarded `ScreenViewSet.perform_destroy` with the real "still assigned" guard. Task 4's `resolve_screen(project, item_type)` reads this model directly.

- [ ] **Step 1: Write the failing tests**

Create `boards/tests/test_screen_assignments_api.py`:

```python
import pytest

from boards.models import ProjectScreenAssignment, Screen


@pytest.mark.django_db
def test_anonymous_callers_are_rejected(client, project):
    assert client.get(f"/api/projects/{project.id}/screen-assignments/").status_code == 403


@pytest.mark.django_db
def test_a_non_member_cannot_view_assignments(auth_client, other_user):
    from projects.models import Project, ProjectMembership

    foreign = Project.objects.create(key="FOREIGN", name="Not Yours")
    ProjectMembership.objects.create(project=foreign, user=other_user, role="owner")

    assert auth_client.get(f"/api/projects/{foreign.id}/screen-assignments/").status_code == 403


@pytest.mark.django_db
def test_a_fresh_project_has_no_assignments(auth_client, project):
    response = auth_client.get(f"/api/projects/{project.id}/screen-assignments/")
    assert response.status_code == 200
    assert response.json() == {
        "epic": None, "story": None, "task": None, "bug": None, "subtask": None,
    }


@pytest.mark.django_db
def test_owner_can_assign_a_screen(auth_client, project):
    screen = Screen.objects.create(name="Bug screen")
    response = auth_client.put(
        f"/api/projects/{project.id}/screen-assignments/", {"task": screen.id}, content_type="application/json"
    )
    assert response.status_code == 200
    assert response.json()["task"] == screen.id
    assert ProjectScreenAssignment.objects.get(project=project, item_type="task").screen_id == screen.id


@pytest.mark.django_db
def test_a_plain_member_cannot_assign_a_screen(auth_client, project):
    from projects.models import ProjectMembership

    ProjectMembership.objects.filter(project=project, user__username="alice").update(role="member")
    screen = Screen.objects.create(name="Bug screen")
    response = auth_client.put(
        f"/api/projects/{project.id}/screen-assignments/", {"task": screen.id}, content_type="application/json"
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_setting_an_assignment_to_null_clears_it(auth_client, project):
    screen = Screen.objects.create(name="Bug screen")
    ProjectScreenAssignment.objects.create(project=project, item_type="task", screen=screen)

    response = auth_client.put(
        f"/api/projects/{project.id}/screen-assignments/", {"task": None}, content_type="application/json"
    )
    assert response.status_code == 200
    assert response.json()["task"] is None
    assert not ProjectScreenAssignment.objects.filter(project=project, item_type="task").exists()


@pytest.mark.django_db
def test_reassigning_an_item_type_replaces_the_old_screen(auth_client, project):
    screen_a = Screen.objects.create(name="A")
    screen_b = Screen.objects.create(name="B")
    ProjectScreenAssignment.objects.create(project=project, item_type="task", screen=screen_a)

    response = auth_client.put(
        f"/api/projects/{project.id}/screen-assignments/", {"task": screen_b.id}, content_type="application/json"
    )
    assert response.status_code == 200
    assert ProjectScreenAssignment.objects.filter(project=project, item_type="task").count() == 1
    assert ProjectScreenAssignment.objects.get(project=project, item_type="task").screen_id == screen_b.id


@pytest.mark.django_db
def test_an_invalid_item_type_key_is_rejected(auth_client, project):
    screen = Screen.objects.create(name="Bug screen")
    response = auth_client.put(
        f"/api/projects/{project.id}/screen-assignments/",
        {"not_a_type": screen.id},
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_assigning_a_nonexistent_screen_is_rejected(auth_client, project):
    response = auth_client.put(
        f"/api/projects/{project.id}/screen-assignments/", {"task": 999999}, content_type="application/json"
    )
    assert response.status_code == 400
    assert not ProjectScreenAssignment.objects.filter(project=project, item_type="task").exists()


@pytest.mark.django_db
def test_assignments_are_scoped_per_project(auth_client, project, user):
    from projects.models import Project, ProjectMembership

    other_project = Project.objects.create(key="OTHER", name="Elsewhere")
    ProjectMembership.objects.create(project=other_project, user=user, role="owner")
    screen = Screen.objects.create(name="Shared screen")

    auth_client.put(f"/api/projects/{project.id}/screen-assignments/", {"task": screen.id}, content_type="application/json")
    response = auth_client.get(f"/api/projects/{other_project.id}/screen-assignments/")

    assert response.json()["task"] is None


@pytest.mark.django_db
def test_deleting_a_screen_still_assigned_somewhere_is_rejected(auth_client, project):
    """The real guard on ScreenViewSet.perform_destroy, now that
    ProjectScreenAssignment exists — Task 2 left this endpoint unguarded
    since it was introduced before this model was."""
    screen = Screen.objects.create(name="In use")
    ProjectScreenAssignment.objects.create(project=project, item_type="task", screen=screen)

    response = auth_client.delete(f"/api/screens/{screen.id}/")
    assert response.status_code == 400
    assert Screen.objects.filter(id=screen.id).exists()
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `docker compose run --rm web pytest boards/tests/test_screen_assignments_api.py -v`
Expected: FAIL — `ImportError` (`ProjectScreenAssignment` doesn't exist yet).

- [ ] **Step 3: Add the model**

In `boards/models.py`, add after `ScreenField`:

```python
class ProjectScreenAssignment(models.Model):
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="screen_assignments")
    item_type = models.CharField(max_length=10, choices=WorkItem.ItemType.choices)
    screen = models.ForeignKey(Screen, on_delete=models.CASCADE, related_name="assignments")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["project", "item_type"], name="unique_screen_assignment_per_item_type"),
        ]

    def __str__(self) -> str:
        return f"{self.project} {self.item_type} -> {self.screen}"
```

```bash
docker compose run --rm web python manage.py makemigrations boards -n project_screen_assignment
```

Confirm the generated file is `boards/migrations/0016_project_screen_assignment.py`.

- [ ] **Step 4: Add the permission helper**

In `boards/serializers.py`, add next to `user_can_manage_definitions`:

```python
def can_manage_screen_assignments(role):
    return role in ("owner", "admin")
```

- [ ] **Step 5: Add the view**

In `boards/views.py`, add `from django.db import transaction` to the imports (not currently present in this file), update the `from .models import ...` line to include `ProjectScreenAssignment`, the `.serializers import (...)` block to include `can_manage_screen_assignments`, and add `from rest_framework.views import APIView` to the imports. Add the view after `ComponentViewSet`:

```python
class ProjectScreenAssignmentsView(APIView):
    permission_classes = [IsAuthenticated, IsProjectMember]

    def get_project(self):
        from projects.models import Project

        project = get_object_or_404(Project, pk=self.kwargs["project_pk"])
        self.check_object_permissions(self.request, project)
        return project

    def _serialize(self, project):
        rows = dict(
            ProjectScreenAssignment.objects.filter(project=project).values_list("item_type", "screen_id")
        )
        return {item_type: rows.get(item_type) for item_type in WorkItem.ItemType.values}

    def get(self, request, project_pk=None):
        return Response(self._serialize(self.get_project()))

    def put(self, request, project_pk=None):
        project = self.get_project()
        role = project.memberships.get(user=request.user).role
        if not can_manage_screen_assignments(role):
            raise PermissionDenied("Only this project's Owner or Admins can change screen assignments.")

        updates = {}
        for item_type, screen_id in request.data.items():
            if item_type not in WorkItem.ItemType.values:
                raise ValidationError({item_type: "Invalid item type."})
            if screen_id is not None and not Screen.objects.filter(pk=screen_id).exists():
                raise ValidationError({item_type: "That screen no longer exists."})
            updates[item_type] = screen_id

        with transaction.atomic():
            for item_type, screen_id in updates.items():
                if screen_id is None:
                    ProjectScreenAssignment.objects.filter(project=project, item_type=item_type).delete()
                else:
                    ProjectScreenAssignment.objects.update_or_create(
                        project=project, item_type=item_type, defaults={"screen_id": screen_id}
                    )

        return Response(self._serialize(project))
```

Also replace `ScreenViewSet.perform_destroy` (Task 2 left it unguarded, since `ProjectScreenAssignment` didn't exist yet) with the real guard:

```python
    def perform_destroy(self, instance):
        if not user_can_manage_definitions(self.request.user):
            raise PermissionDenied(
                "Only a project Owner can manage custom fields. You're not an Owner of any project."
            )
        assigned = list(
            ProjectScreenAssignment.objects.filter(screen=instance)
            .select_related("project")
            .values_list("project__key", "item_type")
        )
        if assigned:
            labels = [f"{key} · {item_type}" for key, item_type in assigned]
            raise ValidationError(
                {"detail": f'"{instance.name}" is still assigned to {", ".join(labels)}. Unassign it first.'}
            )
        instance.delete()
```

- [ ] **Step 6: Wire the URL**

In `boards/urls.py`, update the import to include `ProjectScreenAssignmentsView`, and add:

```python
    path(
        "projects/<int:project_pk>/screen-assignments/",
        ProjectScreenAssignmentsView.as_view(),
        name="project-screen-assignments",
    ),
```

- [ ] **Step 7: Run the tests to confirm they pass**

Run: `docker compose run --rm web pytest boards/tests/test_screen_assignments_api.py -v`
Expected: 11 passed.

Run: `docker compose run --rm web pytest -v`
Expected: all tests pass (234 total).

- [ ] **Step 8: Commit**

```bash
git add boards/
git commit -m "Add ProjectScreenAssignment model and endpoint"
```

---

## Task 4: `WorkItemFieldValue` and `custom_fields` on `WorkItemSerializer`

**Files:**
- Create: `boards/migrations/0017_work_item_field_value.py`
- Modify: `boards/models.py`, `boards/services.py`, `boards/serializers.py`
- Test: `boards/tests/test_work_item_custom_fields.py`

**Interfaces:**
- Consumes: `CustomField`, `FieldOption`, `ScreenField`, `ProjectScreenAssignment` (Tasks 1–3), `WorkItemSerializer.validate()`'s existing pattern (sub-project 2a).
- Produces: `boards.models.WorkItemFieldValue` (`work_item`, `field`, `value`; unique together on `(work_item, field, value)`). `boards.services.custom_fields_read_map(work_item) -> dict[str, Any]`, `boards.services.custom_fields_write_error(project, item_type, payload, existing_item=None) -> dict | str | None`, `boards.services.apply_custom_fields(work_item, payload) -> None`. `WorkItemSerializer` gains `custom_fields` on read and write. Also replaces Task 1's unguarded `FieldOptionViewSet.perform_destroy` with the real "still chosen" guard.

- [ ] **Step 1: Write the failing tests**

Create `boards/tests/test_work_item_custom_fields.py`:

```python
import pytest

from boards.models import Board, CustomField, FieldOption, ProjectScreenAssignment, Screen, ScreenField, WorkItem, WorkItemFieldValue


@pytest.fixture
def board(user, project):
    return Board.objects.create(name="Test Board", created_by=user, project=project)


@pytest.fixture
def screen_with_all_types(project):
    """One screen carrying one field of every type, assigned to Task items
    on `project`. `text_short` is required; everything else is optional, so
    each type's own test can isolate exactly what it's checking."""
    screen = Screen.objects.create(name="Full screen")
    fields = {}
    for field_type in [
        "text_short", "text_long", "number", "date",
        "select", "multiselect", "checkbox", "user_picker",
    ]:
        field = CustomField.objects.create(name=field_type, field_type=field_type, created_by=None)
        fields[field_type] = field
        required = field_type == "text_short"
        ScreenField.objects.create(
            screen=screen, field=field,
            position=len(fields) - 1, required=required,
        )
    FieldOption.objects.create(field=fields["select"], label="High", position=0)
    FieldOption.objects.create(field=fields["select"], label="Low", position=1)
    FieldOption.objects.create(field=fields["multiselect"], label="Red", position=0)
    FieldOption.objects.create(field=fields["multiselect"], label="Blue", position=1)
    ProjectScreenAssignment.objects.create(project=project, item_type="task", screen=screen)
    return fields


@pytest.mark.django_db
def test_no_screen_assigned_means_custom_fields_are_rejected(auth_client, board):
    field = CustomField.objects.create(name="Points", field_type="number", created_by=None)
    response = auth_client.post(
        "/api/work-items/",
        {"board": board.id, "title": "X", "custom_fields": {str(field.id): 5}},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "custom_fields" in response.json()


@pytest.mark.django_db
def test_no_screen_assigned_but_no_custom_fields_submitted_still_works(auth_client, board):
    response = auth_client.post(
        "/api/work-items/", {"board": board.id, "title": "X"}, content_type="application/json"
    )
    assert response.status_code == 201


@pytest.mark.django_db
def test_a_field_not_on_the_screen_is_rejected(auth_client, board, screen_with_all_types):
    stray = CustomField.objects.create(name="Not on screen", field_type="text_short", created_by=None)
    response = auth_client.post(
        "/api/work-items/",
        {
            "board": board.id, "item_type": "task", "title": "X",
            "custom_fields": {
                str(screen_with_all_types["text_short"].id): "ok",
                str(stray.id): "nope",
            },
        },
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "custom_fields" in response.json()


@pytest.mark.django_db
def test_a_missing_required_field_is_rejected(auth_client, board, screen_with_all_types):
    response = auth_client.post(
        "/api/work-items/", {"board": board.id, "item_type": "task", "title": "X"}, content_type="application/json"
    )
    assert response.status_code == 400
    assert "custom_fields" in response.json()


@pytest.mark.django_db
def test_a_valid_submission_round_trips(auth_client, board, screen_with_all_types):
    fields = screen_with_all_types
    response = auth_client.post(
        "/api/work-items/",
        {
            "board": board.id, "item_type": "task", "title": "X",
            "custom_fields": {str(fields["text_short"].id): "ok"},
        },
        content_type="application/json",
    )
    assert response.status_code == 201
    assert response.json()["custom_fields"] == {str(fields["text_short"].id): "ok"}


@pytest.mark.django_db
@pytest.mark.parametrize(
    "field_type,value,expected",
    [
        ("text_short", "hi", "hi"),
        ("text_long", "a much longer paragraph of notes", "a much longer paragraph of notes"),
        ("number", 4.5, "4.5"),
        ("date", "2026-08-20", "2026-08-20"),
        ("checkbox", True, True),
    ],
)
def test_each_simple_type_accepts_a_valid_value(auth_client, board, screen_with_all_types, field_type, value, expected):
    fields = screen_with_all_types
    payload = {str(fields["text_short"].id): "required ok", str(fields[field_type].id): value}
    response = auth_client.post(
        "/api/work-items/",
        {"board": board.id, "item_type": "task", "title": "X", "custom_fields": payload},
        content_type="application/json",
    )
    assert response.status_code == 201
    got = response.json()["custom_fields"][str(fields[field_type].id)]
    if field_type == "number":
        assert float(got) == float(expected)
    else:
        assert got == expected


@pytest.mark.django_db
@pytest.mark.parametrize(
    "field_type,value",
    [
        ("number", "not a number"),
        ("date", "20-08-2026"),
        ("date", "not a date"),
    ],
)
def test_each_simple_type_rejects_an_invalid_value(auth_client, board, screen_with_all_types, field_type, value):
    fields = screen_with_all_types
    payload = {str(fields["text_short"].id): "required ok", str(fields[field_type].id): value}
    response = auth_client.post(
        "/api/work-items/",
        {"board": board.id, "item_type": "task", "title": "X", "custom_fields": payload},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "custom_fields" in response.json()


@pytest.mark.django_db
def test_text_short_over_255_characters_is_rejected(auth_client, board, screen_with_all_types):
    fields = screen_with_all_types
    payload = {str(fields["text_short"].id): "x" * 256}
    response = auth_client.post(
        "/api/work-items/",
        {"board": board.id, "item_type": "task", "title": "X", "custom_fields": payload},
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_select_accepts_a_current_option(auth_client, board, screen_with_all_types):
    fields = screen_with_all_types
    option = fields["select"].options.get(label="High")
    payload = {str(fields["text_short"].id): "ok", str(fields["select"].id): option.id}
    response = auth_client.post(
        "/api/work-items/",
        {"board": board.id, "item_type": "task", "title": "X", "custom_fields": payload},
        content_type="application/json",
    )
    assert response.status_code == 201
    assert response.json()["custom_fields"][str(fields["select"].id)] == option.id


@pytest.mark.django_db
def test_select_rejects_an_option_id_that_does_not_exist(auth_client, board, screen_with_all_types):
    fields = screen_with_all_types
    payload = {str(fields["text_short"].id): "ok", str(fields["select"].id): 999999}
    response = auth_client.post(
        "/api/work-items/",
        {"board": board.id, "item_type": "task", "title": "X", "custom_fields": payload},
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_multiselect_accepts_several_current_options_and_stores_multiple_rows(auth_client, board, screen_with_all_types):
    fields = screen_with_all_types
    red = fields["multiselect"].options.get(label="Red")
    blue = fields["multiselect"].options.get(label="Blue")
    payload = {str(fields["text_short"].id): "ok", str(fields["multiselect"].id): [red.id, blue.id]}
    response = auth_client.post(
        "/api/work-items/",
        {"board": board.id, "item_type": "task", "title": "X", "custom_fields": payload},
        content_type="application/json",
    )
    assert response.status_code == 201
    item = WorkItem.objects.get(title="X")
    assert WorkItemFieldValue.objects.filter(work_item=item, field=fields["multiselect"]).count() == 2
    assert sorted(response.json()["custom_fields"][str(fields["multiselect"].id)]) == sorted([red.id, blue.id])


@pytest.mark.django_db
def test_multiselect_rejects_an_option_not_on_the_field(auth_client, board, screen_with_all_types):
    fields = screen_with_all_types
    red = fields["multiselect"].options.get(label="Red")
    payload = {str(fields["text_short"].id): "ok", str(fields["multiselect"].id): [red.id, 999999]}
    response = auth_client.post(
        "/api/work-items/",
        {"board": board.id, "item_type": "task", "title": "X", "custom_fields": payload},
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_user_picker_accepts_a_project_member(auth_client, board, screen_with_all_types, user):
    fields = screen_with_all_types
    payload = {str(fields["text_short"].id): "ok", str(fields["user_picker"].id): user.id}
    response = auth_client.post(
        "/api/work-items/",
        {"board": board.id, "item_type": "task", "title": "X", "custom_fields": payload},
        content_type="application/json",
    )
    assert response.status_code == 201
    assert response.json()["custom_fields"][str(fields["user_picker"].id)] == user.id


@pytest.mark.django_db
def test_user_picker_rejects_a_non_member(auth_client, board, screen_with_all_types, other_user):
    fields = screen_with_all_types
    payload = {str(fields["text_short"].id): "ok", str(fields["user_picker"].id): other_user.id}
    response = auth_client.post(
        "/api/work-items/",
        {"board": board.id, "item_type": "task", "title": "X", "custom_fields": payload},
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_editing_only_the_title_leaves_custom_field_values_untouched(auth_client, board, screen_with_all_types):
    fields = screen_with_all_types
    create = auth_client.post(
        "/api/work-items/",
        {
            "board": board.id, "item_type": "task", "title": "Before",
            "custom_fields": {str(fields["text_short"].id): "keep me"},
        },
        content_type="application/json",
    )
    item_id = create.json()["id"]

    response = auth_client.patch(
        f"/api/work-items/{item_id}/", {"title": "After"}, content_type="application/json"
    )
    assert response.status_code == 200
    assert response.json()["custom_fields"][str(fields["text_short"].id)] == "keep me"


@pytest.mark.django_db
def test_a_required_field_already_saved_stays_satisfied_on_an_unrelated_edit(auth_client, board, screen_with_all_types):
    fields = screen_with_all_types
    create = auth_client.post(
        "/api/work-items/",
        {
            "board": board.id, "item_type": "task", "title": "Before",
            "custom_fields": {str(fields["text_short"].id): "already set"},
        },
        content_type="application/json",
    )
    item_id = create.json()["id"]

    response = auth_client.patch(
        f"/api/work-items/{item_id}/",
        {"custom_fields": {str(fields["number"].id): 3}},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["custom_fields"][str(fields["text_short"].id)] == "already set"
    assert response.json()["custom_fields"][str(fields["number"].id)] == "3"


@pytest.mark.django_db
def test_clearing_a_required_field_on_edit_is_rejected(auth_client, board, screen_with_all_types):
    fields = screen_with_all_types
    create = auth_client.post(
        "/api/work-items/",
        {
            "board": board.id, "item_type": "task", "title": "Before",
            "custom_fields": {str(fields["text_short"].id): "set"},
        },
        content_type="application/json",
    )
    item_id = create.json()["id"]

    response = auth_client.patch(
        f"/api/work-items/{item_id}/",
        {"custom_fields": {str(fields["text_short"].id): ""}},
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_viewing_a_work_item_shows_a_saved_value_even_after_its_field_leaves_the_screen(
    auth_client, board, screen_with_all_types, project
):
    fields = screen_with_all_types
    create = auth_client.post(
        "/api/work-items/",
        {
            "board": board.id, "item_type": "task", "title": "X",
            "custom_fields": {str(fields["text_short"].id): "kept forever"},
        },
        content_type="application/json",
    )
    item_id = create.json()["id"]

    # Reassign the project's Task screen to a brand-new, unrelated screen —
    # the old field is now orphaned from the currently-assigned screen.
    empty_screen = Screen.objects.create(name="Empty")
    ProjectScreenAssignment.objects.filter(project=project, item_type="task").update(screen=empty_screen)

    response = auth_client.get(f"/api/work-items/{item_id}/")
    assert response.status_code == 200
    assert response.json()["custom_fields"][str(fields["text_short"].id)] == "kept forever"


@pytest.mark.django_db
def test_removing_a_field_from_a_screen_does_not_delete_saved_values(auth_client, board, screen_with_all_types):
    """Belongs conceptually with Task 2's ScreenField removal, but
    WorkItemFieldValue doesn't exist until this task — so it lives here."""
    fields = screen_with_all_types
    create = auth_client.post(
        "/api/work-items/",
        {
            "board": board.id, "item_type": "task", "title": "X",
            "custom_fields": {str(fields["text_short"].id): "keep me"},
        },
        content_type="application/json",
    )
    item_id = create.json()["id"]
    # `screen_with_all_types` builds exactly one screen, so this field
    # appears on exactly one ScreenField row.
    row = ScreenField.objects.get(field=fields["text_short"])

    auth_client.delete(f"/api/screens/{row.screen_id}/fields/{row.id}/")

    assert WorkItemFieldValue.objects.filter(work_item_id=item_id, field=fields["text_short"]).exists()


@pytest.mark.django_db
def test_deleting_an_option_still_used_by_a_work_item_value_is_rejected(auth_client, board, screen_with_all_types):
    """Belongs conceptually with Task 1's FieldOption deletion, but
    WorkItemFieldValue doesn't exist until this task — so it lives here."""
    fields = screen_with_all_types
    option = fields["select"].options.get(label="High")
    auth_client.post(
        "/api/work-items/",
        {
            "board": board.id, "item_type": "task", "title": "X",
            "custom_fields": {str(fields["text_short"].id): "ok", str(fields["select"].id): option.id},
        },
        content_type="application/json",
    )

    response = auth_client.delete(f"/api/fields/{fields['select'].id}/options/{option.id}/")
    assert response.status_code == 400
    assert FieldOption.objects.filter(id=option.id).exists()
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `docker compose run --rm web pytest boards/tests/test_work_item_custom_fields.py -v`
Expected: FAIL — `ImportError` (`WorkItemFieldValue` doesn't exist yet).

- [ ] **Step 3: Add the model**

In `boards/models.py`, add after `ProjectScreenAssignment`:

```python
class WorkItemFieldValue(models.Model):
    work_item = models.ForeignKey(WorkItem, on_delete=models.CASCADE, related_name="field_values")
    field = models.ForeignKey(CustomField, on_delete=models.CASCADE, related_name="values")
    value = models.TextField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["work_item", "field", "value"], name="unique_work_item_field_value"),
        ]

    def __str__(self) -> str:
        return f"{self.field}={self.value!r} on {self.work_item}"
```

```bash
docker compose run --rm web python manage.py makemigrations boards -n work_item_field_value
```

Confirm the generated file is `boards/migrations/0017_work_item_field_value.py`.

- [ ] **Step 4: Add the validation and apply functions to `boards/services.py`**

At the top of `boards/services.py`, add:

```python
import datetime
import re

from .models import CustomField, ProjectScreenAssignment, ScreenField, WorkItem, WorkItemFieldValue
```

(This supplements the existing `from .models import WorkItem` — remove the old bare import line since the new one already includes `WorkItem`.)

Add, after `next_position` and before `move_work_item` (or anywhere at module level — order doesn't matter to Python, only to a human reader, and grouping the custom-fields functions together is clearer):

```python
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _is_iso_date(value) -> bool:
    text = str(value)
    if not _ISO_DATE_RE.match(text):
        return False
    try:
        datetime.date.fromisoformat(text)
    except ValueError:
        return False
    return True


def is_blank_custom_value(field_type, value) -> bool:
    """Mirrors design/js/logic.js's isBlankValue exactly: blankness is
    per-type, not a single "falsy" check."""
    if field_type == CustomField.FieldType.MULTISELECT:
        return not isinstance(value, list) or len(value) == 0
    if field_type == CustomField.FieldType.CHECKBOX:
        return value is not True
    return value is None or (isinstance(value, str) and not value.strip()) or value == ""


def field_value_error(field, value, option_ids, member_ids):
    """Type-checks one value against its field. Returns a message, or None
    when it's fine. Mirrors design/js/logic.js's fieldValueError exactly."""
    field_type = field.field_type

    if field_type == CustomField.FieldType.TEXT_SHORT:
        return f'"{field.name}" must be 255 characters or fewer.' if len(str(value)) > 255 else None
    if field_type == CustomField.FieldType.TEXT_LONG:
        return None
    if field_type == CustomField.FieldType.NUMBER:
        try:
            float(str(value).strip())
        except (TypeError, ValueError):
            return f'"{field.name}" must be a number.'
        return None
    if field_type == CustomField.FieldType.DATE:
        return None if _is_iso_date(value) else f'"{field.name}" must be a date (YYYY-MM-DD).'
    if field_type == CustomField.FieldType.CHECKBOX:
        return None
    if field_type == CustomField.FieldType.SELECT:
        try:
            ok = int(value) in option_ids
        except (TypeError, ValueError):
            ok = False
        return None if ok else f'"{field.name}" must be one of its current options.'
    if field_type == CustomField.FieldType.MULTISELECT:
        try:
            ok = all(int(v) in option_ids for v in value)
        except (TypeError, ValueError):
            ok = False
        return None if ok else f'"{field.name}" must only use its current options.'
    if field_type == CustomField.FieldType.USER_PICKER:
        try:
            ok = int(value) in member_ids
        except (TypeError, ValueError):
            ok = False
        return None if ok else f'"{field.name}" must be a member of this project.'
    return f'"{field.name}" has an unknown field type.'


def resolve_screen(project, item_type):
    assignment = (
        ProjectScreenAssignment.objects.filter(project=project, item_type=item_type)
        .select_related("screen")
        .first()
    )
    return assignment.screen if assignment else None


def custom_fields_read_map(work_item):
    """Every saved value for this work item, keyed by field id (as a
    string, matching JSON object key semantics) — regardless of whether
    its field is still on the currently-assigned screen. Mirrors
    design/js/store.js's customFieldsOf's `map` half exactly."""
    values_by_field = {}
    for value in work_item.field_values.select_related("field"):
        values_by_field.setdefault(value.field, []).append(value)

    result = {}
    for field, rows in values_by_field.items():
        key = str(field.id)
        if field.field_type == CustomField.FieldType.MULTISELECT:
            result[key] = [int(row.value) for row in rows]
        elif field.field_type == CustomField.FieldType.CHECKBOX:
            result[key] = True
        elif field.field_type in (CustomField.FieldType.SELECT, CustomField.FieldType.USER_PICKER):
            result[key] = int(rows[0].value)
        else:
            result[key] = rows[0].value
    return result


def custom_fields_write_error(project, item_type, payload, existing_item=None):
    """None if the payload is fine, else a dict of {field_id: message} (or,
    for the no-screen-assigned case, a single string) suitable for
    `serializers.ValidationError({"custom_fields": <this>})`. Mirrors
    design/js/store.js's customFieldsError exactly."""
    screen = resolve_screen(project, item_type)

    if screen is None:
        if not payload:
            return None
        label = dict(WorkItem.ItemType.choices)[item_type]
        return (
            f"{label} items in this project have no screen assigned, "
            f"so custom fields can't be set on them."
        )

    rows = list(ScreenField.objects.filter(screen=screen).select_related("field").order_by("position", "id"))
    allowed_ids = {row.field_id for row in rows}

    stray = {}
    for key in payload:
        try:
            key_id = int(key)
        except (TypeError, ValueError):
            stray[key] = "That field isn't on this screen."
            continue
        if key_id not in allowed_ids:
            field = CustomField.objects.filter(pk=key_id).first()
            name = f'"{field.name}"' if field else "That field"
            stray[key] = f'{name} isn\'t on the "{screen.name}" screen.'
    if stray:
        return stray

    existing_map = custom_fields_read_map(existing_item) if existing_item else {}
    member_ids = set(project.memberships.values_list("user_id", flat=True))

    errors = {}
    for row in rows:
        field = row.field
        key = str(field.id)
        value = payload[key] if key in payload else existing_map.get(key)

        if is_blank_custom_value(field.field_type, value):
            if row.required:
                errors[key] = f'"{field.name}" is required.'
            continue

        option_ids = set(field.options.values_list("id", flat=True)) if field.has_options else set()
        message = field_value_error(field, value, option_ids, member_ids)
        if message:
            errors[key] = message

    return errors or None


def apply_custom_fields(work_item, payload):
    """Upsert-by-replacement: every field named in the payload loses all of
    its existing rows first, then gets the new one (or several, for
    multiselect). A blank value clears the field. Mirrors
    design/js/store.js's applyCustomFields exactly."""
    for key, raw in (payload or {}).items():
        try:
            field = CustomField.objects.get(pk=int(key))
        except (CustomField.DoesNotExist, TypeError, ValueError):
            continue
        WorkItemFieldValue.objects.filter(work_item=work_item, field=field).delete()
        if is_blank_custom_value(field.field_type, raw):
            continue
        values = raw if field.field_type == CustomField.FieldType.MULTISELECT else [raw]
        seen = set()
        for v in values:
            text = str(v)
            if text in seen:
                continue
            seen.add(text)
            WorkItemFieldValue.objects.create(work_item=work_item, field=field, value=text)
```

- [ ] **Step 5: Wire `custom_fields` into `WorkItemSerializer`**

In `boards/serializers.py`, add to the top-level import:

```python
from .services import apply_custom_fields, custom_fields_read_map, custom_fields_write_error
```

Replace the entire `WorkItemSerializer` class (this supersedes sub-project 2a's version — it keeps every existing field, the hierarchy `validate()` logic, and the components-project-match check unchanged, and adds `custom_fields`):

```python
class WorkItemSerializer(serializers.ModelSerializer):
    assignee_detail = UserSerializer(source="assignee", read_only=True)
    created_by = UserSerializer(read_only=True)
    priority_label = serializers.CharField(source="get_priority_display", read_only=True)
    parent_detail = WorkItemSummarySerializer(source="parent", read_only=True)
    components_detail = ComponentSerializer(source="components", many=True, read_only=True)
    custom_fields = serializers.DictField(required=False, write_only=True)

    class Meta:
        model = WorkItem
        fields = [
            "id", "key", "board", "item_type", "title", "description",
            "status", "priority", "priority_label", "due_date",
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

        if "custom_fields" in attrs:
            board = attrs.get("board") or (self.instance.board if self.instance else None)
            item_type = attrs.get("item_type") or (
                self.instance.item_type if self.instance else WorkItem.ItemType.TASK
            )
            error = custom_fields_write_error(
                board.project, item_type, attrs["custom_fields"], existing_item=self.instance
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

Also replace `FieldOptionViewSet.perform_destroy` (Task 1 left it unguarded, since `WorkItemFieldValue` didn't exist yet) with the real guard, in `boards/views.py`:

```python
    def perform_destroy(self, instance):
        if not user_can_manage_definitions(self.request.user):
            raise PermissionDenied(
                "Only a project Owner can manage custom fields. You're not an Owner of any project."
            )
        from .models import WorkItemFieldValue

        if WorkItemFieldValue.objects.filter(field=instance.field, value=str(instance.pk)).exists():
            raise ValidationError(
                {"detail": f'"{instance.label}" is still chosen on a work item. Clear it there first.'}
            )
        field = instance.field
        instance.delete()
        siblings = list(FieldOption.objects.filter(field=field).order_by("position", "id"))
        for index, option in enumerate(siblings):
            if option.position != index:
                option.position = index
                option.save(update_fields=["position"])
```

- [ ] **Step 6: Run the tests to confirm they pass**

Run: `docker compose run --rm web pytest boards/tests/test_work_item_custom_fields.py -v`
Expected: 26 passed (20 test functions, two of which — `test_each_simple_type_accepts_a_valid_value` and `test_each_simple_type_rejects_an_invalid_value` — are `@pytest.mark.parametrize`d into 5 and 3 cases respectively: 18 plain tests + 5 + 3 = 26).

Run: `docker compose run --rm web pytest -v`
Expected: all tests pass (260 total).

- [ ] **Step 7: Commit**

```bash
git add boards/
git commit -m "Add WorkItemFieldValue model and custom_fields on WorkItemSerializer"
```

---

## Task 5: Admin registration, documentation, and final regression

**Files:**
- Modify: `boards/admin.py`, `docs/api.md`

**Interfaces:**
- Consumes: everything from Tasks 1–4.
- Produces: nothing new — this task makes the new models visible in `/admin/` (for support/debugging, matching every prior model in this app) and brings `docs/api.md` up to date, which `CLAUDE.md` requires reading before writing client code.

- [ ] **Step 1: Register the new models in `boards/admin.py`**

Add to `boards/admin.py`, after the existing registrations:

```python
from .models import CustomField, FieldOption, ProjectScreenAssignment, Screen, ScreenField, WorkItemFieldValue


class FieldOptionInline(admin.TabularInline):
    model = FieldOption
    extra = 0


@admin.register(CustomField)
class CustomFieldAdmin(admin.ModelAdmin):
    list_display = ["name", "field_type", "created_by", "created_at"]
    list_filter = ["field_type"]
    search_fields = ["name"]
    inlines = [FieldOptionInline]


class ScreenFieldInline(admin.TabularInline):
    model = ScreenField
    extra = 0


@admin.register(Screen)
class ScreenAdmin(admin.ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]
    inlines = [ScreenFieldInline]


@admin.register(ProjectScreenAssignment)
class ProjectScreenAssignmentAdmin(admin.ModelAdmin):
    list_display = ["project", "item_type", "screen"]
    list_filter = ["item_type"]


@admin.register(WorkItemFieldValue)
class WorkItemFieldValueAdmin(admin.ModelAdmin):
    list_display = ["work_item", "field", "value"]
    list_filter = ["field"]
```

(Update the existing `from .models import ...` line at the top of the file, or add the second import line above it — either is fine, this file doesn't currently have more than one such line so adding a second is simplest.)

- [ ] **Step 2: Update `docs/api.md`**

Read the current `docs/api.md` in full first — this plan doesn't reproduce it, since it changes with every sub-project and this task must extend whatever is there, not overwrite it. Add a new section (matching the existing section style for Components/Work Item Links from sub-project 2a) documenting:

- `GET/POST /api/fields/`, `GET/PATCH/DELETE /api/fields/{id}/`, `POST /api/fields/{field_id}/options/`, `PATCH/DELETE /api/fields/{field_id}/options/{id}/` — who can call each (any authenticated user for `GET`; Owner of any project for writes), and the field_type-immutability and delete-guard 400s.
- `GET/POST /api/screens/`, `GET/PATCH/DELETE /api/screens/{id}/`, `POST /api/screens/{screen_id}/fields/`, `PATCH/DELETE /api/screens/{screen_id}/fields/{id}/` — same permission tier, plus the assigned-screen delete guard.
- `GET/PUT /api/projects/{id}/screen-assignments/` — project Owner/Admin for `PUT`, any project member for `GET`; body/response shape `{epic, story, task, bug, subtask} -> screen id | null`.
- The `custom_fields` addition to `WorkItemSerializer`'s existing `/api/work-items/` documentation: read shape, write shape, and the three ways a write can 400 (no screen assigned, field not on screen, required/type-check failure) all keyed under `"custom_fields"`.

Also add a line to `docs/api.md`'s top-level behaviours-that-bite section (the one `CLAUDE.md` points at) noting: **`custom_fields` values are never trusted as already the right type — every value is coerced and checked server-side against the field's `field_type`, exactly mirroring `design/js/logic.js`'s `fieldValueError`.**

- [ ] **Step 3: Run the full suite one more time**

Run: `docker compose run --rm web pytest -v`
Expected: all tests pass (261 total — unchanged from the end of Task 4; this step exists to catch anything Task 5's admin.py edit might have broken, e.g. a typo in the `from .models import` line).

- [ ] **Step 4: Commit**

```bash
git add boards/admin.py docs/api.md
git commit -m "Register Custom Fields & Screens models in admin, document the new endpoints"
```

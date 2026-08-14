from django.conf import settings
from django.db import models, transaction


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

    class ItemType(models.TextChoices):
        EPIC = "epic", "Epic"
        STORY = "story", "Story"
        TASK = "task", "Task"
        BUG = "bug", "Bug"
        SUBTASK = "subtask", "Subtask"

    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name="work_items")
    title = models.CharField(max_length=200)
    key = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.TODO
    )
    priority = models.IntegerField(
        choices=Priority.choices, default=Priority.MEDIUM
    )
    item_type = models.CharField(max_length=10, choices=ItemType.choices, default=ItemType.TASK)
    due_date = models.DateField(null=True, blank=True)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_work_items",
    )
    parent = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="children"
    )
    components = models.ManyToManyField("Component", blank=True, related_name="work_items")
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

    def save(self, *args, **kwargs):
        # `key` is required+unique, so it must always be populated before the
        # row hits the database. A freshly instantiated WorkItem's `key` is
        # falsy (Django's CharField default, absent an explicit value) no
        # matter how it's created — via the API, a fixture, the admin, a
        # management command, or a data migration — so this is the single
        # place key generation happens; there is no separate copy of this
        # logic in the view. Unlike `services.next_position()`, which is
        # deliberately unlocked and self-healing because a collision there
        # just means a harmless re-sort, a duplicate `key` is a real
        # correctness bug — hence the real `select_for_update()` lock here,
        # not a lock-free retry. The lock, the counter increment, and the
        # INSERT itself all happen inside one atomic block, so a failure in
        # the INSERT rolls back the counter increment too instead of
        # permanently burning a key number.
        if not self.key:
            from projects.models import Project

            with transaction.atomic():
                project = Project.objects.select_for_update().get(pk=self.board.project_id)
                self.key = f"{project.key}-{project.next_item_number}"
                project.next_item_number += 1
                project.save(update_fields=["next_item_number"])
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)


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

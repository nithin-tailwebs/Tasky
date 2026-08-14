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
        # row hits the database. The API path (WorkItemViewSet.perform_create)
        # generates it up front, under the same project-scoped, row-locked
        # counter, and passes it in — so `self.key` is already set by the
        # time save() runs there and this is a no-op. This fallback exists
        # for every other path that creates a WorkItem directly (fixtures,
        # tests, the admin, management commands, data migrations): without
        # it, every such create would hit the same blank default and collide
        # on the unique constraint after the first one. Unlike
        # `services.next_position()`, which is deliberately unlocked and
        # self-healing because a collision there just means a harmless
        # re-sort, a duplicate `key` is a real correctness bug — hence the
        # real `select_for_update()` lock here, not a lock-free retry.
        if not self.key:
            from projects.models import Project

            with transaction.atomic():
                project = Project.objects.select_for_update().get(pk=self.board.project_id)
                self.key = f"{project.key}-{project.next_item_number}"
                project.next_item_number += 1
                project.save(update_fields=["next_item_number"])
        super().save(*args, **kwargs)


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

from django.conf import settings
from django.db import models


class Project(models.Model):
    key = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    next_item_number = models.IntegerField(default=1)
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

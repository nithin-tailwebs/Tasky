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

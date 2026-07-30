from django.contrib import admin

from .models import Board


@admin.register(Board)
class BoardAdmin(admin.ModelAdmin):
    list_display = ["name", "created_by", "created_at"]
    search_fields = ["name"]


from .models import Card


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = ["title", "board", "status", "priority", "assignee", "due_date"]
    list_filter = ["status", "priority", "board"]
    search_fields = ["title", "description"]

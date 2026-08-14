from rest_framework import serializers

from accounts.serializers import UserSerializer

from .models import Board, Comment, Component, WorkItem

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


def can_manage_components(role):
    return role in ("owner", "admin")


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


class ComponentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Component
        fields = ["id", "project", "name"]
        read_only_fields = ["project"]

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("This field may not be blank.")
        return value.strip()


class WorkItemSummarySerializer(serializers.ModelSerializer):
    """Enough to identify and link to another work item, without pulling
    its full field set — used for parent_detail and the children list."""

    class Meta:
        model = WorkItem
        fields = ["id", "key", "title", "item_type", "status"]


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

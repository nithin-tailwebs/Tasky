from rest_framework import serializers

from accounts.serializers import UserSerializer

from .models import Board, Card, Comment


class BoardSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)

    class Meta:
        model = Board
        fields = ["id", "project", "name", "description", "created_by", "created_at", "updated_at"]


class CardSerializer(serializers.ModelSerializer):
    assignee_detail = UserSerializer(source="assignee", read_only=True)
    created_by = UserSerializer(read_only=True)
    priority_label = serializers.CharField(source="get_priority_display", read_only=True)

    class Meta:
        model = Card
        fields = [
            "id", "board", "title", "description",
            "status", "priority", "priority_label", "due_date",
            "assignee", "assignee_detail",
            "position", "created_by", "created_at", "updated_at",
        ]
        read_only_fields = ["position"]


class MoveCardSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Card.Status.choices)
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

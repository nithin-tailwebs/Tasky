from rest_framework import serializers

from accounts.serializers import UserSerializer

from .models import Board


class BoardSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)

    class Meta:
        model = Board
        fields = ["id", "name", "description", "created_by", "created_at", "updated_at"]

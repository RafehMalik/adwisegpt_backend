from rest_framework import serializers
from .models import UserPreference

class UserPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPreference
        fields = [
            "complete_opt_out",
            "contextual_advertising",
            "interest_categories",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]

    def validate_interest_categories(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Interest categories must be a list.")
        return value
    



from rest_framework import serializers


class ChatMessageSerializer(serializers.Serializer):
    message_type = serializers.CharField()
    content = serializers.CharField()
    timestamp = serializers.DateTimeField()


class SessionSerializer(serializers.Serializer):
    session_id = serializers.CharField()
    title = serializers.CharField()
    last_activity = serializers.DateTimeField()
    message_count = serializers.IntegerField()
    last_message_preview = serializers.CharField()


class AdDetailSerializer(serializers.Serializer):
    """Ad details for UI"""
    id = serializers.IntegerField()
    title = serializers.CharField()
    description = serializers.CharField()
    url = serializers.URLField()
    click_url = serializers.URLField()  # Backend tracking URL
    media_url = serializers.URLField(allow_null=True)
    category = serializers.CharField()


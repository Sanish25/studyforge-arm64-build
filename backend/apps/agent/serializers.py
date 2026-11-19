"""Request body for POST /api/v1/agent/pandu/."""

from rest_framework import serializers


class PanduAgentSerializer(serializers.Serializer):
    """Thin client payload: message + optional course/conversation/doc context."""

    message = serializers.CharField(allow_blank=True, max_length=8_000, trim_whitespace=False)
    course_id = serializers.IntegerField(required=False, min_value=1)
    conversation_id = serializers.IntegerField(required=False, min_value=1)
    document_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_empty=True,
        max_length=20,
    )

    def validate_document_ids(self, value):
        if len(set(value)) != len(value):
            raise serializers.ValidationError("document_ids must be unique.")
        return value

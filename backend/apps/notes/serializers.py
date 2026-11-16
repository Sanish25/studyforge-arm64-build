from rest_framework import serializers

from apps.notes.llm import NoteOptions
from apps.notes.models import CourseNotes, DetailLevel, NoteFormat, NoteType, StudyGuide
from apps.notes.selectors import get_source_documents

MAX_SOURCE_DOCUMENTS = 20


class GenerateCourseNotesSerializer(serializers.Serializer):
    document_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
        max_length=MAX_SOURCE_DOCUMENTS,
        error_messages={"empty": "Select at least one material."},
    )
    # Fixed lists only: anything else is a 400 before the model is called.
    # Omitted options fall back to how notes were generated before SCRUM-86.
    note_type = serializers.ChoiceField(choices=NoteType.choices, default=NoteType.OUTLINE)
    detail_level = serializers.ChoiceField(choices=DetailLevel.choices, default=DetailLevel.STANDARD)
    format = serializers.ChoiceField(choices=NoteFormat.choices, default=NoteFormat.BULLETS)

    def validate_document_ids(self, value):
        if len(set(value)) != len(value):
            raise serializers.ValidationError("Each document can be selected only once.")
        return value

    def get_options(self):
        data = self.validated_data
        return NoteOptions(
            note_type=data["note_type"], detail_level=data["detail_level"], format=data["format"]
        )


class CourseNotesSerializer(serializers.ModelSerializer):
    options = serializers.SerializerMethodField()
    source_documents = serializers.SerializerMethodField()

    class Meta:
        model = CourseNotes
        fields = ["id", "title", "course", "options", "overview", "sections", "source_documents", "created_at"]
        read_only_fields = fields

    def get_options(self, notes):
        return {
            "note_type": notes.note_type,
            "detail_level": notes.detail_level,
            "format": notes.format,
        }

    def get_source_documents(self, notes):
        return get_source_documents(notes)


class StudyGuideSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudyGuide
        fields = ["key_concepts", "important_points", "summary"]
        read_only_fields = fields
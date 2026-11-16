from django.conf import settings
from django.db import models


# Fixed option lists. Only these keys ever select prompt text; no student
# free text reaches the model (SCRUM-86).
class NoteType(models.TextChoices):
    SUMMARY = "summary", "Summary"
    OUTLINE = "outline", "Outline"
    KEY_CONCEPTS = "key_concepts", "Key concepts"


class DetailLevel(models.TextChoices):
    BRIEF = "brief", "Brief"
    STANDARD = "standard", "Standard"
    DETAILED = "detailed", "Detailed"


class NoteFormat(models.TextChoices):
    BULLETS = "bullets", "Bullet points"
    PARAGRAPHS = "paragraphs", "Paragraphs"


class CourseNotes(models.Model):
    """Notes generated from one or more materials in a course.

    Each generation is a new row, so a later set of notes never overwrites
    one built from a different selection.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="course_notes",
    )
    course = models.ForeignKey(
        "courses.Course",
        on_delete=models.CASCADE,
        related_name="course_notes",
    )
    title = models.CharField(max_length=255)
    overview = models.TextField()
    # [{"heading": str, "key_concepts": [{"term": str, "explanation": str}],
    #   "points": [str]}], shaped by validate_course_notes. With the paragraphs
    # format each point is a paragraph; the shape is the same.
    sections = models.JSONField(default=list)
    # The defaults are what notes looked like before options existed.
    note_type = models.CharField(max_length=20, choices=NoteType.choices, default=NoteType.OUTLINE)
    detail_level = models.CharField(max_length=20, choices=DetailLevel.choices, default=DetailLevel.STANDARD)
    format = models.CharField(max_length=20, choices=NoteFormat.choices, default=NoteFormat.BULLETS)
    model_name = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "course notes"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(note_type__in=NoteType.values), name="course_notes_note_type_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(detail_level__in=DetailLevel.values), name="course_notes_detail_level_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(format__in=NoteFormat.values), name="course_notes_format_valid"
            ),
        ]

    def __str__(self):
        return self.title


class NoteSource(models.Model):
    """One material a set of notes was built from.

    `document_id` is a plain external identifier, never a foreign key: the
    same shape as the processing service's Execution.document_id (SCRUM-98).
    Deleting the material deletes the notes; see apps.notes.signals.
    """

    notes = models.ForeignKey(CourseNotes, on_delete=models.CASCADE, related_name="sources")
    document_id = models.PositiveBigIntegerField(db_index=True)
    # Upload order, which is the order the materials were given to the model.
    position = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["position"]
        constraints = [
            models.CheckConstraint(condition=models.Q(document_id__gt=0), name="note_source_document_positive"),
            models.UniqueConstraint(fields=["notes", "document_id"], name="note_source_unique_document"),
            models.UniqueConstraint(fields=["notes", "position"], name="note_source_unique_position"),
        ]

    def __str__(self):
        return f"Document {self.document_id} for notes {self.notes_id}"


class StudyGuide(models.Model):
    """Generated notes for one document. One guide per document;
    regenerating overwrites it."""

    document = models.OneToOneField(
        "documents.Document",
        on_delete=models.CASCADE,
        related_name="study_guide",
    )
    key_concepts = models.JSONField(default=list)
    important_points = models.JSONField(default=list)
    summary = models.TextField(blank=True)
    model_name = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Study guide for document {self.document_id}"